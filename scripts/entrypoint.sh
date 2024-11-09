#!/bin/sh

set -e

manage migrate
daphne -b 0.0.0.0 -p $PORT "gyrinx.asgi:application"
