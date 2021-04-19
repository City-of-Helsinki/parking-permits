#!/bin/bash

set -e

if [[ "$WAIT_FOR_IT_ADDRESS" ]]; then
    ./wait-for-it.sh $WAIT_FOR_IT_ADDRESS --timeout=30
fi

if [[ "$DEV_SERVER" = "true" ]]; then
    python /app/manage.py runserver 0.0.0.0:8000
else
    gunicorn
fi
