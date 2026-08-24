#!/usr/bin/env bash

PYTORCH_BACKEND_CONFIG="${PYTORCH_BACKEND_CONFIG:-${ROOT_DIR}/config/pytorch-backends.conf}"

compute_matrix_value() {
  local key="$1"
  awk -F= -v key="${key}" '$1 == key { print substr($0, index($0, "=") + 1); exit }' \
    "${PYTORCH_BACKEND_CONFIG}"
}

compute_backend_field() {
  local backend="$1"
  local field="$2"
  local column
  case "${field}" in
    requires_gpu) column=2 ;;
    minimum_cuda) column=3 ;;
    index_url) column=4 ;;
    *) return 1 ;;
  esac
  awk -F'[=|]' -v backend="${backend}" -v column="${column}" \
    '$1 == "BACKEND" && $2 == backend { print $(column + 1); exit }' \
    "${PYTORCH_BACKEND_CONFIG}"
}

compute_backend_exists() {
  [[ -n "$(compute_backend_field "$1" index_url)" ]]
}

compute_version_le() {
  awk -v left="$1" -v right="$2" 'BEGIN {
    split(left, l, ".")
    split(right, r, ".")
    l_major = l[1] + 0
    l_minor = l[2] + 0
    r_major = r[1] + 0
    r_minor = r[2] + 0
    exit !((l_major < r_major) || (l_major == r_major && l_minor <= r_minor))
  }'
}

compute_select_cuda_backend() {
  local detected_cuda="$1"
  local selected="" selected_min="0" name requires_gpu minimum_cuda
  while IFS='|' read -r name requires_gpu minimum_cuda _; do
    [[ -n "${name}" && "${requires_gpu}" == "true" ]] || continue
    if compute_version_le "${minimum_cuda}" "${detected_cuda}" && \
       compute_version_le "${selected_min}" "${minimum_cuda}"; then
      selected="${name}"
      selected_min="${minimum_cuda}"
    fi
  done < <(awk -F= '$1 == "BACKEND" { print substr($0, index($0, "=") + 1) }' "${PYTORCH_BACKEND_CONFIG}")
  [[ -n "${selected}" ]] || return 1
  printf '%s' "${selected}"
}

compute_resolve() {
  local requested="$1"
  local gpu_usable="$2"
  local detected_cuda="$3"
  local os_name="$4"
  local architecture="$5"
  local engine="$6"
  local selected="cpu"

  COMPUTE_RESOLUTION_REASON=""
  case "${requested}" in
    cpu)
      COMPUTE_RESOLVED_BACKEND="cpu"
      COMPUTE_RESOLVED_DEVICE="cpu"
      return 0
      ;;
    auto|gpu) ;;
    *)
      COMPUTE_RESOLUTION_REASON="unsupported compute mode: ${requested}"
      return 1
      ;;
  esac

  if [[ "${os_name}" != "Linux" || "${architecture}" != "x86_64" ]]; then
    COMPUTE_RESOLUTION_REASON="GPU mode requires Linux x86_64; detected ${os_name} ${architecture}"
  elif [[ "${engine}" != "docker" ]]; then
    COMPUTE_RESOLUTION_REASON="GPU mode currently requires Docker; detected ${engine:-no container engine}"
  elif [[ "${gpu_usable}" != "true" ]]; then
    COMPUTE_RESOLUTION_REASON="Docker could not verify access to an NVIDIA GPU"
  elif ! selected="$(compute_select_cuda_backend "${detected_cuda}")"; then
    COMPUTE_RESOLUTION_REASON="no supported PyTorch backend matches CUDA ${detected_cuda:-unknown}"
  else
    COMPUTE_RESOLVED_BACKEND="${selected}"
    COMPUTE_RESOLVED_DEVICE="cuda"
    return 0
  fi

  if [[ "${requested}" == "auto" ]]; then
    COMPUTE_RESOLVED_BACKEND="cpu"
    COMPUTE_RESOLVED_DEVICE="cpu"
    return 0
  fi
  return 1
}

compute_is_gpu_backend() {
  [[ "$(compute_backend_field "$1" requires_gpu)" == "true" ]]
}
