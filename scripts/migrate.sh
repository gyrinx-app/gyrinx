#!/bin/bash

set -e


docker compose run -T app manage makemigrations core content
