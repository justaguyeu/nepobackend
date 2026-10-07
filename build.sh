#!/usr/bin/env bash
# Render build command: ./build.sh
# Installs dependencies and applies database migrations on every deploy,
# so new tables/columns exist before the new code starts serving requests.
set -o errexit

pip install -r requirements.txt
python manage.py migrate --no-input
