#!/bin/bash

set -e


docker compose run -T app pytest
