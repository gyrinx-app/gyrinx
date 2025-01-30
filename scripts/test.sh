#!/bin/bash

set -e


docker compose run --remove-orphans -T app pytest
