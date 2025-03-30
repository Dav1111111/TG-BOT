#!/bin/bash

# Скрипт для запуска телеграм-бота

# Переходим в директорию проекта
cd "$(dirname "$0")/Marketing Bot TG/project"

# Активируем виртуальное окружение, если оно есть
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Запускаем бота
python3 main.py 