#!/usr/bin/env bash
# Build and install the vendored HiggsTools python package (Higgs module).
#
# Usage:
#   scripts/build_higgstools.sh
#
# Installs into the active virtualenv if one is active, otherwise into a
# project-local virtualenv at build/venv (created if missing).
#
# Requirements: python3 (>=3.7), cmake (>=3.17), a C++17 compiler.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HIGGSTOOLS_SRC="${DHB_HIGGSTOOLS_ROOT:-${ROOT}/lib/higgstools-v1.2}"
VENV_DIR="${DHB_BUILD_ROOT:-${ROOT}/build}/venv"

if [[ ! -f "${HIGGSTOOLS_SRC}/pyproject.toml" ]]; then
    echo "[build_higgstools] ERROR: HiggsTools source not found at ${HIGGSTOOLS_SRC}" >&2
    exit 1
fi

if ! command -v cmake >/dev/null 2>&1; then
    echo "[build_higgstools] ERROR: cmake not found (>=3.17 required)" >&2
    exit 1
fi

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    PYTHON="${VIRTUAL_ENV}/bin/python"
    echo "[build_higgstools] Using active virtualenv: ${VIRTUAL_ENV}"
else
    if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
        echo "[build_higgstools] Creating virtualenv at ${VENV_DIR}"
        python3 -m venv "${VENV_DIR}"
    fi
    PYTHON="${VENV_DIR}/bin/python"
    echo "[build_higgstools] Using project virtualenv: ${VENV_DIR}"
    echo "[build_higgstools] (activate with: source ${VENV_DIR}/bin/activate)"
fi

"${PYTHON}" -m pip install --upgrade pip >/dev/null

echo "[build_higgstools] Installing HiggsTools from ${HIGGSTOOLS_SRC} (this compiles C++, please wait)"
"${PYTHON}" -m pip install "${HIGGSTOOLS_SRC}"

echo "[build_higgstools] Verifying import"
"${PYTHON}" - <<'EOF'
import Higgs
import Higgs.predictions
import Higgs.bounds
import Higgs.signals
print("[build_higgstools] OK: Higgs module version", getattr(Higgs, "__version__", "unknown"))
EOF
