#!/bin/bash
# Подключение сетевой папки и запуск прода. Всё, что делает скрипт перед
# стартом контейнеров, нужно для одного: чтобы /app/excel внутри контейнера был
# смонтированной шарой, а не пустым каталогом.
#
# Запуск: cd <repo>/infra && sudo ./mount_and_start.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOUNT_POINT="${MOUNT_POINT:-/mnt/ktm-disk}"
SHARE_PATH="${SHARE_PATH:-//172.17.11.7/Оператор}" # Укажите актуальный IP/хост
CREDS_FILE="${CREDS_FILE:-/etc/ekranchik-credentials}"
# Без x-systemd.idle-timeout: при простое systemd отмонтировал бы шару, и
# контейнер, пересозданный в это окно, привязался бы к пустому каталогу.
MOUNT_EXTRA="nofail,_netdev,x-systemd.automount"

# 0. Устанавливаем клиент CIFS, если его нет
if ! command -v mount.cifs >/dev/null 2>&1; then
    echo "Установка cifs-utils (требуется sudo)..."
    sudo apt-get update -qq && sudo apt-get install -y -qq cifs-utils
fi

# 1. Проверяем / создаем файл учетных данных
if [ ! -f "$CREDS_FILE" ] && [ ! -f "${CREDS_FILE}-guest" ]; then
    echo "Учетные данные для сетевого диска не найдены."
    echo "Если сетевая папка открыта для всех (гостевой доступ без пароля), просто нажмите Enter."
    read -r -p "Введите имя пользователя SMB (или Enter для гостевого доступа): " smb_user

    if [ -z "$smb_user" ]; then
        echo "Выбран гостевой доступ (без авторизации)."
        # Создаем пустой файл-маркер, чтобы не спрашивать в следующий раз
        sudo touch "${CREDS_FILE}-guest"
    else
        read -r -s -p "Введите пароль SMB: " smb_pass
        echo ""
        read -r -p "Введите домен SMB (оставьте пустым, если нет): " smb_domain

        echo "Сохранение учетных данных в $CREDS_FILE (требуется sudo)..."
        sudo bash -c "cat > $CREDS_FILE" <<EOF
username=$smb_user
password=$smb_pass
EOF
        if [ -n "$smb_domain" ]; then
            sudo bash -c "echo 'domain=$smb_domain' >> $CREDS_FILE"
        fi
        sudo chmod 600 "$CREDS_FILE"
        echo "Учетные данные сохранены с безопасными правами доступа."
    fi
fi

# 2. Создаем точку монтирования
if [ ! -d "$MOUNT_POINT" ]; then
    echo "Создание каталога монтирования $MOUNT_POINT (требуется sudo)..."
    sudo mkdir -p "$MOUNT_POINT"
fi

# 3. Настройка параметров монтирования в зависимости от авторизации
if [ -f "${CREDS_FILE}-guest" ]; then
    MOUNT_OPTS="guest,iocharset=utf8,ro,file_mode=0444,dir_mode=0555"
    FSTAB_LINE="$SHARE_PATH $MOUNT_POINT cifs guest,iocharset=utf8,ro,file_mode=0444,dir_mode=0555,$MOUNT_EXTRA 0 0"
else
    MOUNT_OPTS="credentials=$CREDS_FILE,iocharset=utf8,ro,file_mode=0444,dir_mode=0555"
    FSTAB_LINE="$SHARE_PATH $MOUNT_POINT cifs credentials=$CREDS_FILE,iocharset=utf8,ro,file_mode=0444,dir_mode=0555,$MOUNT_EXTRA 0 0"
fi

# 4. Настройка fstab для автоподключения при перезагрузке. Строка переписывается
# целиком, если она отличается от нужной: раньше скрипт только добавлял строку,
# и оставшийся от прежних запусков `x-systemd.idle-timeout=60` жил дальше —
# шара отмонтировалась на простое.
if ! grep -qxF "$FSTAB_LINE" /etc/fstab; then
    echo "Запись $MOUNT_POINT в /etc/fstab (автоподключение при загрузке)..."
    sudo cp /etc/fstab /etc/fstab.ekranchik.bak
    fstab_tmp="$(mktemp)"
    grep -vF "$MOUNT_POINT" /etc/fstab > "$fstab_tmp" || true
    printf '%s\n' "$FSTAB_LINE" >> "$fstab_tmp"
    sudo cp "$fstab_tmp" /etc/fstab
    rm -f "$fstab_tmp"
    sudo systemctl daemon-reload
fi

# 5. Монтируем диск (если не смонтирован)
if mountpoint -q "$MOUNT_POINT"; then
    echo "Сетевой диск уже смонтирован в $MOUNT_POINT"
else
    echo "Монтирование сетевого диска..."
    if [ -f "${CREDS_FILE}-guest" ]; then
        sudo mount -t cifs -o "$MOUNT_OPTS" "$SHARE_PATH" "$MOUNT_POINT"
    else
        sudo mount "$MOUNT_POINT"
    fi
    echo "Сетевой диск успешно смонтирован!"
fi

# 6. Проверка монтирования до старта контейнеров: пустой каталог вместо шары —
# самая частая причина «Файл не найден» при живой книге.
mountpoint -q "$MOUNT_POINT" || {
    echo "ОШИБКА: $MOUNT_POINT не является точкой монтирования — контейнер получит пустой /app/excel" >&2
    exit 1
}
[ -n "$(ls -A "$MOUNT_POINT" 2>/dev/null)" ] || {
    echo "ОШИБКА: $MOUNT_POINT смонтирован, но пуст — серверу нечего читать" >&2
    exit 1
}
echo "Сетевой диск на месте: $MOUNT_POINT ($(ls -A "$MOUNT_POINT" | wc -l) записей)"

# 7. Запуск Docker Compose — через общий скрипт: он же проверяет, что книга
# видна изнутри контейнера, и падает с кодом 1, если нет.
echo "Запуск Docker Compose через deploy_prod.sh..."
exec "$SCRIPT_DIR/deploy_prod.sh" "$@"
