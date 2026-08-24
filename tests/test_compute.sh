#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "${ROOT_DIR}/scripts/lib/compute.sh"
. "${ROOT_DIR}/scripts/lib/hardware.sh"
. "${ROOT_DIR}/scripts/lib/env.sh"
. "${ROOT_DIR}/scripts/lib/compose.sh"

fail_test() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_eq() {
  [[ "$1" == "$2" ]] || fail_test "expected '$2', got '$1'${3:+ ($3)}"
}

assert_contains() {
  [[ "$1" == *"$2"* ]] || fail_test "expected output to contain '$2'"
}

assert_eq "$(compute_matrix_value PYTORCH_VERSION)" "2.12.1" "matrix version"
compute_backend_exists cpu || fail_test "cpu backend missing"
compute_backend_exists cu132 || fail_test "cu132 backend missing"
if compute_backend_exists unsupported; then fail_test "unsupported backend accepted"; fi

if compute_select_cuda_backend 12.5 >/dev/null; then fail_test "CUDA 12.5 should be unsupported"; fi
assert_eq "$(compute_select_cuda_backend 12.6)" "cu126"
assert_eq "$(compute_select_cuda_backend 12.10)" "cu126"
assert_eq "$(compute_select_cuda_backend 13.1)" "cu130"
assert_eq "$(compute_select_cuda_backend 13.2)" "cu132"
assert_eq "$(compute_select_cuda_backend 14.0)" "cu132"

compute_resolve cpu false 0 Linux x86_64 podman
assert_eq "${COMPUTE_RESOLVED_BACKEND}" "cpu"
assert_eq "${COMPUTE_RESOLVED_DEVICE}" "cpu"

compute_resolve auto false 0 Linux x86_64 docker
assert_eq "${COMPUTE_RESOLVED_BACKEND}" "cpu"
assert_contains "${COMPUTE_RESOLUTION_REASON}" "could not verify"

if compute_resolve gpu false 13.2 Linux x86_64 docker; then
  fail_test "explicit GPU request should fail without container GPU visibility"
fi
assert_contains "${COMPUTE_RESOLUTION_REASON}" "could not verify"

compute_resolve gpu true 13.1 Linux x86_64 docker
assert_eq "${COMPUTE_RESOLVED_BACKEND}" "cu130"
assert_eq "${COMPUTE_RESOLVED_DEVICE}" "cuda"

dry_run="$(bash "${ROOT_DIR}/scripts/install-python-dependencies.sh" --backend cpu --dry-run "${ROOT_DIR}/requirements/base.txt")"
assert_contains "${dry_run}" "torch==2.12.1"
assert_contains "${dry_run}" "https://download.pytorch.org/whl/cpu"
if bash "${ROOT_DIR}/scripts/install-python-dependencies.sh" --backend invalid --dry-run "${ROOT_DIR}/requirements/base.txt" >/dev/null 2>&1; then
  fail_test "dependency installer accepted an invalid backend"
fi

hardware_storage_requirements 5 cpu false
assert_eq "${STORAGE_RUNTIME_MIN_GB}" "15"
assert_eq "${STORAGE_RUNTIME_RECOMMENDED_GB}" "25"
assert_eq "${STORAGE_DOCKER_MIN_GB}" "10"
assert_eq "${STORAGE_DOCKER_RECOMMENDED_GB}" "15"

hardware_storage_requirements 5 cu132 true
assert_eq "${STORAGE_RUNTIME_MIN_GB}" "35"
assert_eq "${STORAGE_RUNTIME_RECOMMENDED_GB}" "55"
assert_eq "${STORAGE_DOCKER_MIN_GB}" "35"

temp_dir="$(mktemp -d)"
env_file="${temp_dir}/stack.env"
trap 'rm -f "${env_file}"; rmdir "${temp_dir}"' EXIT
printf 'KEEP=user-value\nCOMPUTE_MODE=auto\n' > "${env_file}"
env_set_var "${env_file}" COMPUTE_MODE gpu
env_set_var "${env_file}" PYTORCH_BACKEND cu132
assert_contains "$(cat "${env_file}")" "KEEP=user-value"
assert_contains "$(cat "${env_file}")" "COMPUTE_MODE=gpu"
assert_contains "$(cat "${env_file}")" "PYTORCH_BACKEND=cu132"
assert_eq "$(grep -c '^COMPUTE_MODE=' "${env_file}")" "1"

assert_eq "$(compose_files_for_scope main cpu)" "docker-compose.yml"
gpu_files="$(compose_files_for_scope dashboard cu130)"
assert_contains "${gpu_files}" "docker-compose.dashboard.yml"
assert_contains "${gpu_files}" "docker-compose.dashboard.gpu.yml"
assert_eq "$(compose_files_for_scope agentic cu126 | tail -n 1)" "docker-compose.agentic-rag.gpu.yml"

printf 'Compute shell tests passed.\n'
