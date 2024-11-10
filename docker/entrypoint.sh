#!/bin/sh

set -e

manage collectstatic --noinput
manage migrate
daphne -b 0.0.0.0 -p $PORT "gyrinx.asgi:application"
