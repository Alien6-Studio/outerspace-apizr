#!/bin/sh
if [ -f "./entrypoint.sh" ]; then
    ./entrypoint.sh
fi

exec gunicorn -c gunicorn.conf.py wsgi:application