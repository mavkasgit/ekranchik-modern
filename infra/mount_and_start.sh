#!/bin/bash
set -e

MOUNT_POINT="/mnt/ktm-disk"
SHARE_PATH="//172.17.11.115/Оператор" # Укажите актуальный IP/хост
CREDS_FILE="/etc/ekranchik-credentials"

# 1. Проверяем / создаем файл учетных данных
if [ ! -f "$CREDS_FILE" ] && [ ! -f "${CREDS_FILE}-guest" ]; then
    echo "Учетные данные для сетевого диска не найдены."
    echo "Если сетевая папка открыта для всех (гостевой доступ без пароля), просто нажмите Enter."
    read -p "Введите имя пользователя SMB (или Enter для гостевого доступа): " smb_user
    
    if [ -z "$smb_user" ]; then
        echo "Выбран гостевой доступ (без авторизации)."
        # Создаем пустой файл-маркер, чтобы не спрашивать в следующий раз
        sudo touch "${CREDS_FILE}-guest"
    else
        read -s -p "Введите пароль SMB: " smb_pass
        echo ""
        read -p "Введите домен SMB (оставьте пустым, если нет): " smb_domain

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
    FSTAB_LINE="$SHARE_PATH $MOUNT_POINT cifs guest,iocharset=utf8,ro,file_mode=0444,dir_mode=0555,nofail 0 0"
else
    MOUNT_OPTS="credentials=$CREDS_FILE,iocharset=utf8,ro,file_mode=0444,dir_mode=0555"
    FSTAB_LINE="$SHARE_PATH $MOUNT_POINT cifs credentials=$CREDS_FILE,iocharset=utf8,ro,file_mode=0444,dir_mode=0555,nofail 0 0"
fi

# 4. Настройка fstab для автоподключения при перезагрузке
if ! grep -qF "$SHARE_PATH" /etc/fstab; then
    echo "Добавление сетевого диска в /etc/fstab для автозапуска при загрузке системы..."
    sudo bash -c "echo '$FSTAB_LINE' >> /etc/fstab"
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

# 6. Запуск Docker
echo "Запуск Docker Compose..."
docker compose -f compose/docker-compose.prod.yml up -d --build
