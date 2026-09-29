#!/bin/bash
# Единственная точка сборки и пересоздания прод-контейнеров.
#
# Зачем: `docker compose up` не готовит сетевой диск на Linux. Если /mnt/ktm-disk
# в этот момент не смонтирован, Docker монтирует пустой каталог, и бэкенд
# получает пустой /app/excel. Со стороны это «Файл не найден» при живой книге
# на шаре, а причина видна только в ошибке выбора пути. Поэтому: сначала диск
# (проверить и при необходимости поднять), потом compose, а после старта —
# проверка, что книга видна уже из контейнера.
#
# На Windows compose-файл тот же: разница в монтировании задана переменными
# EXCEL_VOL_* в infra/compose/.env.
#
# Запуск на прод-сервере:
#   cd <repo>/infra && ./deploy_prod.sh                 # сборка и пересоздание
#   ./deploy_prod.sh --force-recreate backend           # аргументы уходят в `up`
#   ./deploy_prod.sh up -d backend                      # либо своя команда compose
#
# Переменные: MOUNT_POINT (по умолчанию /mnt/ktm-disk), WAIT_SECONDS (60).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MOUNT_POINT="${MOUNT_POINT:-/mnt/ktm-disk}"
WAIT_SECONDS="${WAIT_SECONDS:-60}"
COMPOSE_FILES=(-f compose/docker-compose.prod.yml)

# Версия приложения: единый источник — корневой VERSION. В контекст сборки
# образов он не попадает (контексты — backend/ и frontend/), поэтому значение
# передаётся аргументом сборки, иначе и интерфейс, и /api/version показали бы
# 'dev' — по ним не видно, что пересборка что-то принесла.
APP_VERSION="$(tr -d '[:space:]' < "$SCRIPT_DIR/../VERSION" 2>/dev/null || true)"
APP_VERSION="${APP_VERSION:-dev}"
export APP_VERSION


# Windows и Linux запускаются одним и тем же compose-файлом: разница в
# монтировании сетевого диска задана переменными EXCEL_VOL_* из
# infra/compose/.env, который compose подхватывает сам. На сервере этого
# файла нет, и значения по умолчанию дают тот же bind /mnt/ktm-disk.

fail() {
    echo "[deploy] ОШИБКА: $*" >&2
    exit 1
}

# 1. Сетевой диск. На Linux книга приходит в контейнер из тома excel, который
# compose монтирует на /mnt/ktm-disk, поэтому пустая или отсутствующая точка
# монтирования — это гарантированный пустой /app/excel внутри.
if [ "$(uname -s)" = "Linux" ]; then
    if ! mountpoint -q "$MOUNT_POINT"; then
        echo "[deploy] $MOUNT_POINT не смонтирован — монтирую по /etc/fstab..."
        sudo mount "$MOUNT_POINT" || fail \
            "не удалось смонтировать $MOUNT_POINT: запустите infra/mount_and_start.sh (он настроит учётные данные и fstab)"
    fi
    mountpoint -q "$MOUNT_POINT" || fail \
        "$MOUNT_POINT не является точкой монтирования — контейнер получит пустой /app/excel. Запустите infra/mount_and_start.sh"
    [ -n "$(ls -A "$MOUNT_POINT" 2>/dev/null)" ] || fail \
        "$MOUNT_POINT смонтирован, но пуст — серверу нечего читать. Проверьте доступ к шаре //172.17.11.7/Оператор"
    echo "[deploy] Диск на месте: $MOUNT_POINT ($(ls -A "$MOUNT_POINT" | wc -l) записей)"
fi

# 2. Сборка и пересоздание.
echo "[deploy] Версия сборки: $APP_VERSION"
if [ "$#" -eq 0 ]; then
    echo "[deploy] docker compose ${COMPOSE_FILES[*]} up -d --build"
    docker compose "${COMPOSE_FILES[@]}" up -d --build
else
    echo "[deploy] docker compose ${COMPOSE_FILES[*]} $*"
    docker compose "${COMPOSE_FILES[@]}" "$@"
fi

# 3. Книга должна быть видна изнутри контейнера. Путь берётся из переменной
# самого контейнера (EXCEL_REAL_FILE_PATH) и раскрывается внутри него: в скрипте
# он не дублируется, а через хостовую оболочку кириллица не проходит.
for _ in $(seq 1 "$WAIT_SECONDS"); do
    if docker compose "${COMPOSE_FILES[@]}" exec -T backend sh -c 'test -s "$EXCEL_REAL_FILE_PATH"' 2>/dev/null; then
        echo "[deploy] Книга из EXCEL_REAL_FILE_PATH видна серверу"
        exit 0
    fi
    sleep 1
done

echo "[deploy] Контейнеры:" >&2
docker compose "${COMPOSE_FILES[@]}" ps >&2 || true
echo "[deploy] EXCEL_REAL_FILE_PATH в контейнере:" >&2
docker compose "${COMPOSE_FILES[@]}" exec -T backend printenv EXCEL_REAL_FILE_PATH >&2 || true
echo "[deploy] Последние строки лога backend:" >&2
docker compose "${COMPOSE_FILES[@]}" logs --tail=20 backend >&2 || true
fail "backend не видит книгу из EXCEL_REAL_FILE_PATH за ${WAIT_SECONDS} с"
