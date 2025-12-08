#!/bin/bash

set -e

if [[ "$APPLY_MIGRATIONS" = "True" ]]; then
  echo "Applying migrations..."
  python /app/manage.py migrate --noinput
fi

if [[ "$BOOTSTRAP_PARKING_PERMITS" = "True" ]]; then
    python /app/manage.py bootstrap_parking_permits
fi

if [[ "$INSTALL_PRECOMMIT" = "True" ]]; then
    pre-commit install --overwrite
fi

if [[ "$CREATE_SUPERUSER" = "True" ]]; then
    python /app/manage.py createsuperuser --noinput || true
fi

if [[ "$UPDATE_TRANSLATIONS" = "True" ]]; then
    echo "Updating translations..."
    python /app/manage.py compilemessages -l 'fi'
fi

if [[ "$SEND_MAIL" = "True" && "$DEBUG" = "False" ]]; then
    python /app/manage.py runmailer_pg &
fi

if [[ "$DEV_SERVER" = "True" ]]; then
    python /app/manage.py runserver 0.0.0.0:8888
else
    gunicorn
fi
