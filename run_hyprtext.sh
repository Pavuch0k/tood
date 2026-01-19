#!/usr/bin/env bash

cd /home/nik/tood || exit 1

# Активируем виртуальное окружение, если оно есть
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

exec python3 main.py









