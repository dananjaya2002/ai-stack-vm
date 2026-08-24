#!/usr/bin/env bash

compose_files_for_scope() {
  local scope="$1"
  local backend="$2"
  local base_file overlay_file
  case "${scope}" in
    main)
      base_file="docker-compose.yml"
      overlay_file="docker-compose.gpu.yml"
      ;;
    dashboard)
      base_file="docker-compose.dashboard.yml"
      overlay_file="docker-compose.dashboard.gpu.yml"
      ;;
    agentic)
      base_file="docker-compose.agentic-rag.yml"
      overlay_file="docker-compose.agentic-rag.gpu.yml"
      ;;
    *) return 1 ;;
  esac

  printf '%s\n' "${base_file}"
  if compute_is_gpu_backend "${backend}"; then
    printf '%s\n' "${overlay_file}"
  fi
}
