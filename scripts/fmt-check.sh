#!/bin/bash

npm run fmt-check
if [ $? -ne 0 ]; then
    exit 1
fi
