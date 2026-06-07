#!/usr/bin/env bash

curl -s -X POST http://localhost:9000/ask \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"$1\"}" | jq -r '.answer'
