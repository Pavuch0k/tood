#!/usr/bin/env bash

# Скрипт для установки .desktop файла и ассоциации файлов

DESKTOP_FILE="$HOME/.local/share/applications/hyprtext.desktop"
SOURCE_FILE="$(dirname "$0")/hyprtext.desktop"

# Создаём директорию, если её нет
mkdir -p "$HOME/.local/share/applications"

# Копируем .desktop файл
cp "$SOURCE_FILE" "$DESKTOP_FILE"

# Обновляем кэш desktop-файлов
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo "Desktop файл установлен: $DESKTOP_FILE"
echo "Теперь можно ассоциировать .txt и .md файлы с Hyprtext через настройки системы."

