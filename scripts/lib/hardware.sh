#!/usr/bin/env bash

hardware_have() {
  command -v "$1" >/dev/null 2>&1
}

hardware_existing_path() {
  local path="$1"
  while [[ ! -e "${path}" && "${path}" != "/" ]]; do
    path="$(dirname "${path}")"
  done
  printf '%s' "${path}"
}

hardware_disk_free_gb() {
  local path
  path="$(hardware_existing_path "$1")"
  df -Pk "${path}" 2>/dev/null | awk 'NR == 2 { printf "%d", $4 / 1024 / 1024 }'
}

hardware_disk_device() {
  local path
  path="$(hardware_existing_path "$1")"
  df -Pk "${path}" 2>/dev/null | awk 'NR == 2 { print $1 }'
}

hardware_detect_host() {
  local runtime_home="$1"
  DETECTED_OS="$(uname -s 2>/dev/null || printf 'unknown')"
  DETECTED_ARCH="$(uname -m 2>/dev/null || printf 'unknown')"
  DETECTED_OS_DESCRIPTION="${DETECTED_OS}"
  if [[ -r /etc/os-release ]]; then
    DETECTED_OS_DESCRIPTION="$(awk -F= '$1 == "PRETTY_NAME" { value=substr($0, index($0, "=") + 1); gsub(/^\"|\"$/, "", value); print value; exit }' /etc/os-release)"
  fi
  DETECTED_CPU_CORES="$(command -v nproc >/dev/null 2>&1 && nproc || getconf _NPROCESSORS_ONLN 2>/dev/null || printf '1')"
  DETECTED_RAM_GB="$(awk '/MemTotal/ { printf "%.0f", $2 / 1024 / 1024 }' /proc/meminfo 2>/dev/null || printf '0')"
  DETECTED_AVAILABLE_RAM_GB="$(awk '/MemAvailable/ { printf "%.0f", $2 / 1024 / 1024 }' /proc/meminfo 2>/dev/null || printf '0')"
  DETECTED_RUNTIME_PATH="$(hardware_existing_path "${runtime_home}")"
  DETECTED_RUNTIME_DISK_FREE_GB="$(hardware_disk_free_gb "${runtime_home}")"
  DETECTED_RUNTIME_DISK_DEVICE="$(hardware_disk_device "${runtime_home}")"

  DETECTED_CONTAINER_ENGINE=""
  DETECTED_CONTAINER_ENGINE_VERSION="not detected"
  DETECTED_DOCKER_ROOT="/"
  if hardware_have docker && docker info >/dev/null 2>&1; then
    DETECTED_CONTAINER_ENGINE="docker"
    DETECTED_CONTAINER_ENGINE_VERSION="$(docker --version 2>/dev/null || printf 'unavailable')"
    DETECTED_DOCKER_ROOT="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || printf '/')"
  elif hardware_have podman && podman info >/dev/null 2>&1; then
    DETECTED_CONTAINER_ENGINE="podman"
    DETECTED_CONTAINER_ENGINE_VERSION="$(podman --version 2>/dev/null || printf 'unavailable')"
    DETECTED_DOCKER_ROOT="$(podman info --format '{{.Store.GraphRoot}}' 2>/dev/null || printf '/')"
  fi
  DETECTED_DOCKER_DISK_FREE_GB="$(hardware_disk_free_gb "${DETECTED_DOCKER_ROOT}")"
  DETECTED_DOCKER_DISK_DEVICE="$(hardware_disk_device "${DETECTED_DOCKER_ROOT}")"
}

hardware_detect_nvidia_host() {
  DETECTED_GPU_NAME="none"
  DETECTED_GPU_VRAM_GB="0"
  DETECTED_NVIDIA_DRIVER="not detected"
  DETECTED_CUDA_COMPATIBILITY="0"
  DETECTED_NVIDIA_SMI="unavailable"
  DETECTED_NVIDIA_RUNTIME="not detected"
  DETECTED_CONTAINER_GPU="not tested"

  hardware_have nvidia-smi || return 0
  local gpu_line header
  gpu_line="$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits 2>/dev/null | head -n 1 || true)"
  [[ -n "${gpu_line}" ]] || return 0
  DETECTED_NVIDIA_SMI="available"
  DETECTED_GPU_NAME="$(printf '%s' "${gpu_line%%,*}" | awk '{$1=$1; print}')"
  local remainder vram_mb
  remainder="${gpu_line#*,}"
  vram_mb="$(printf '%s' "${remainder%%,*}" | awk '{$1=$1; print}')"
  DETECTED_GPU_VRAM_GB="$(awk -v mb="${vram_mb}" 'BEGIN { printf "%.0f", mb / 1024 }')"
  DETECTED_NVIDIA_DRIVER="$(printf '%s' "${remainder#*,}" | awk '{$1=$1; print}')"
  header="$(nvidia-smi 2>/dev/null | head -n 3 | tr '\n' ' ' || true)"
  DETECTED_CUDA_COMPATIBILITY="$(printf '%s' "${header}" | sed -n 's/.*CUDA Version:[[:space:]]*\([0-9][0-9.]*\).*/\1/p')"
  DETECTED_CUDA_COMPATIBILITY="${DETECTED_CUDA_COMPATIBILITY:-0}"
}

hardware_probe_container_gpu() {
  local pull_policy="${1:-missing}"
  DETECTED_CONTAINER_GPU="unavailable"
  [[ "${DETECTED_CONTAINER_ENGINE}" == "docker" ]] || return 1
  if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -qi nvidia; then
    DETECTED_NVIDIA_RUNTIME="registered"
  else
    DETECTED_NVIDIA_RUNTIME="not listed"
  fi
  if docker run --rm --pull="${pull_policy}" --gpus all ubuntu:24.04 nvidia-smi -L >/dev/null 2>&1; then
    DETECTED_CONTAINER_GPU="available"
    return 0
  fi
  return 1
}

hardware_same_storage_device() {
  [[ -n "${DETECTED_RUNTIME_DISK_DEVICE}" && \
     "${DETECTED_RUNTIME_DISK_DEVICE}" == "${DETECTED_DOCKER_DISK_DEVICE}" ]]
}

hardware_storage_requirements() {
  local remaining_model_gb="$1"
  local backend="$2"
  local shared_filesystem="$3"
  local runtime_min runtime_recommended docker_min docker_recommended

  runtime_min=$((remaining_model_gb + 10))
  runtime_recommended=$((remaining_model_gb + 20))
  if [[ "${backend}" == "cpu" ]]; then
    docker_min=10
    docker_recommended=15
  else
    docker_min=20
    docker_recommended=30
  fi

  if [[ "${shared_filesystem}" == "true" ]]; then
    STORAGE_RUNTIME_MIN_GB=$((runtime_min + docker_min))
    STORAGE_RUNTIME_RECOMMENDED_GB=$((runtime_recommended + docker_recommended))
    STORAGE_DOCKER_MIN_GB="${STORAGE_RUNTIME_MIN_GB}"
    STORAGE_DOCKER_RECOMMENDED_GB="${STORAGE_RUNTIME_RECOMMENDED_GB}"
  else
    STORAGE_RUNTIME_MIN_GB="${runtime_min}"
    STORAGE_RUNTIME_RECOMMENDED_GB="${runtime_recommended}"
    STORAGE_DOCKER_MIN_GB="${docker_min}"
    STORAGE_DOCKER_RECOMMENDED_GB="${docker_recommended}"
  fi
}
