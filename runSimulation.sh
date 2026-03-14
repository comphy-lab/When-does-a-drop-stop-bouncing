#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT_DIR/src-local/params.sh"

usage() {
  cat <<'EOF'
Usage: bash runSimulation.sh [case-params-file]

Compile and run the Basilisk case defined by a parameter file.
Defaults to ./case.params.

The parameter file must define at least:
  CaseNo, MAXlevel, tmax, tsnap, We, Ohd, Ohs, Bo, Ldomain

Optional keys:
  OMP_NUM_THREADS, QCC, QCCFLAGS, SOLVER_NAME
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

PARAM_FILE="${1:-$ROOT_DIR/case.params}"
if [[ ! -f "$PARAM_FILE" ]]; then
  echo "Parameter file not found: $PARAM_FILE" >&2
  exit 1
fi

CASE_NO="$(require_param_value "$PARAM_FILE" "CaseNo")"
if [[ ! "$CASE_NO" =~ ^[0-9]+$ ]]; then
  echo "CaseNo must be a non-negative integer in $PARAM_FILE" >&2
  exit 1
fi

CASE_DIR="$ROOT_DIR/simulationCases/$CASE_NO"
mkdir -p "$CASE_DIR/intermediate"

CASE_PARAMS_PATH="$CASE_DIR/case.params"
cp "$PARAM_FILE" "$CASE_PARAMS_PATH"

SOLVER_NAME="$(get_param_value "$CASE_PARAMS_PATH" "SOLVER_NAME")"
SOLVER_NAME="${SOLVER_NAME:-bounce}"
QCC_BIN="$(get_param_value "$CASE_PARAMS_PATH" "QCC")"
QCC_BIN="${QCC_BIN:-qcc}"
QCCFLAGS_RAW="$(get_param_value "$CASE_PARAMS_PATH" "QCCFLAGS")"
QCCFLAGS_RAW="${QCCFLAGS_RAW:--fopenmp -Wall -O2}"
OMP_THREADS="$(get_param_value "$CASE_PARAMS_PATH" "OMP_NUM_THREADS")"
OMP_THREADS="${OMP_THREADS:-8}"

if ! command -v "$QCC_BIN" >/dev/null 2>&1 && [[ -x "$ROOT_DIR/basilisk/src/qcc" ]]; then
  QCC_BIN="$ROOT_DIR/basilisk/src/qcc"
fi

read -r -a QCCFLAGS <<< "$QCCFLAGS_RAW"

(
  cd "$CASE_DIR"
  export OMP_NUM_THREADS="$OMP_THREADS"
  "$QCC_BIN" "${QCCFLAGS[@]}" "$ROOT_DIR/simulationCases/bounce.c" -o "$SOLVER_NAME" -lm
  "./$SOLVER_NAME" "case.params"
)
