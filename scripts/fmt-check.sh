#!/bin/bash

npm run fmt-check
if [ $? -ne 0 ]; then
    npm run fmt
    exit 1
fi
