#!/bin/bash

set -e

if [[ "$WAIT_FOR_IT_ADDRESS" ]]; then
    ./wait-for-it.sh $WAIT_FOR_IT_ADDRESS --timeout=30
fi

echo "Applying migrations..."
python /app/manage.py migrate --noinput

if [[ "$BOOTSTRAP_PARKING_PERMITS" = "True" ]]; then
    python /app/manage.py bootstrap_parking_permits
fi

if [[ "$INSTALL_PRECOMMIT" = "True" ]]; then
    pre-commit install --overwrite
fi

if [[ "$CREATE_SUPERUSER" = "True" ]]; then
    python /app/manage.py createsuperuser --noinput || true
fi

echo "Updating translations..."
python /app/manage.py compilemessages -l fi

if [[ "$DEV_SERVER" = "True" ]]; then
    python /app/manage.py runserver 0.0.0.0:8888
else
    gunicorn
fi
