#!/bin/sh

set -e

manage collectstatic --noinput
manage migrate
manage ensuresuperuser --no-input
daphne -b 0.0.0.0 -p $PORT "gyrinx.asgi:application"
