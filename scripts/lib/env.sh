#!/usr/bin/env bash

env_set_var() {
  local env_file="$1"
  local key="$2"
  local value="$3"
  local tmp

  touch "${env_file}"
  tmp="$(mktemp)"
  awk -v key="${key}" -v value="${value}" '
    BEGIN { done = 0 }
    $0 ~ "^" key "=" {
      print key "=" value
      done = 1
      next
    }
    { print }
    END {
      if (!done) {
        print key "=" value
      }
    }
  ' "${env_file}" > "${tmp}"
  mv "${tmp}" "${env_file}"
}
