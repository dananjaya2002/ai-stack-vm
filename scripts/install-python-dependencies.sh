#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/compute.sh
. "${ROOT_DIR}/scripts/lib/compute.sh"

usage() {
  printf 'usage: %s --backend <name> [--dry-run] <requirements-file>...\n' "$0" >&2
  exit 2
}

backend=""
dry_run=0
requirements=()
while (( $# > 0 )); do
  case "$1" in
    --backend)
      [[ $# -ge 2 ]] || usage
      backend="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --*) usage ;;
    *) requirements+=("$1"); shift ;;
  esac
done

[[ -n "${backend}" && ${#requirements[@]} -gt 0 ]] || usage
compute_backend_exists "${backend}" || { printf 'unsupported PyTorch backend: %s\n' "${backend}" >&2; exit 2; }

python_bin="${PYTHON_BIN:-python3}"
pytorch_version="$(compute_matrix_value PYTORCH_VERSION)"
index_url="$(compute_backend_field "${backend}" index_url)"
requires_gpu="$(compute_backend_field "${backend}" requires_gpu)"
constraint="torch==${pytorch_version}"

if (( dry_run == 1 )); then
  printf '%s -m pip install --no-cache-dir %s --index-url %s\n' "${python_bin}" "${constraint}" "${index_url}"
  printf '%s -m pip install --no-cache-dir --constraint <torch-constraint>' "${python_bin}"
  printf ' --requirement %s' "${requirements[@]}"
  printf '\n'
  exit 0
fi

for requirement in "${requirements[@]}"; do
  [[ -f "${requirement}" ]] || { printf 'requirements file not found: %s\n' "${requirement}" >&2; exit 2; }
done

constraint_file="$(mktemp)"
trap 'rm -f "${constraint_file}"' EXIT
printf '%s\n' "${constraint}" > "${constraint_file}"

"${python_bin}" -m pip install --no-cache-dir "${constraint}" --index-url "${index_url}"
pip_args=(--no-cache-dir --constraint "${constraint_file}")
for requirement in "${requirements[@]}"; do
  pip_args+=(--requirement "${requirement}")
done
"${python_bin}" -m pip install "${pip_args[@]}"

"${python_bin}" - "${requires_gpu}" <<'PY'
import sys
import torch

expects_cuda = sys.argv[1] == "true"
has_cuda_wheel = torch.version.cuda is not None
if has_cuda_wheel != expects_cuda:
    raise SystemExit(
        f"PyTorch wheel mismatch: expected CUDA={expects_cuda}, torch.version.cuda={torch.version.cuda!r}"
    )
print(f"PyTorch {torch.__version__}; CUDA wheel: {torch.version.cuda or 'none'}")
PY
