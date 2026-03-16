#!/usr/bin/env bash
# Compile and run one Basilisk case from a `key=value` parameter file.
#
# Responsibilities:
# - resolve the case directory from `CaseNo`
# - preserve per-case parameter files when rerunning an existing case
# - copy the maintained solver/header sources into `simulationCases/<CaseNo>/build/`
# - compile the solver with `qcc`
# - execute the resulting binary inside the case directory
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT_DIR/src-local/params.sh"

usage() {
  cat <<'EOF'
Usage: bash runSimulation.sh [case-params-file]

Compile and run the Basilisk case defined by a parameter file.
Defaults to ./case.params.

The parameter file must define at least:
  CaseNo, MAXlevel, tmax, We, Ohd, Ohs, Bo, Ldomain

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
BUILD_DIR="$CASE_DIR/build"
mkdir -p "$BUILD_DIR/simulationCases" "$BUILD_DIR/src-local"

CASE_PARAMS_PATH="$CASE_DIR/case.params"
if [[ -f "$CASE_PARAMS_PATH" ]]; then
  echo "Using existing case parameters: $CASE_PARAMS_PATH"
elif [[ "$PARAM_FILE" != "$CASE_PARAMS_PATH" ]]; then
  cp "$PARAM_FILE" "$CASE_PARAMS_PATH"
else
  echo "Using case parameters: $CASE_PARAMS_PATH"
fi

cp "$ROOT_DIR/simulationCases/bounce.c" "$BUILD_DIR/simulationCases/bounce.c"
cp "$ROOT_DIR/src-local/"*.h "$BUILD_DIR/src-local/"

# Resolve optional toolchain overrides from the case-local parameter file.
SOLVER_NAME="$(get_param_value "$CASE_PARAMS_PATH" "SOLVER_NAME")"
SOLVER_NAME="${SOLVER_NAME:-bounce}"
QCC_BIN="$(get_param_value "$CASE_PARAMS_PATH" "QCC")"
QCC_BIN="${QCC_BIN:-qcc}"
QCCFLAGS_RAW="$(get_param_value "$CASE_PARAMS_PATH" "QCCFLAGS")"
QCCFLAGS_RAW="${QCCFLAGS_RAW:--Wall -O2}"
OMP_THREADS="$(get_param_value "$CASE_PARAMS_PATH" "OMP_NUM_THREADS")"
OMP_THREADS="${OMP_THREADS:-1}"

if ! command -v "$QCC_BIN" >/dev/null 2>&1 && [[ -x "$ROOT_DIR/basilisk/src/qcc" ]]; then
  QCC_BIN="$ROOT_DIR/basilisk/src/qcc"
fi

read -r -a QCCFLAGS <<< "$QCCFLAGS_RAW"
INCLUDE_FLAGS=("-I$ROOT_DIR/src-local" "-I$BUILD_DIR/src-local")

# Build and execute from the materialized case directory so checkpoints and
# outputs land next to the active `case.params`.
(
  cd "$CASE_DIR"
  export OMP_NUM_THREADS="$OMP_THREADS"
  "$QCC_BIN" "${QCCFLAGS[@]}" "${INCLUDE_FLAGS[@]}" "build/simulationCases/bounce.c" -o "$SOLVER_NAME" -lm
  "./$SOLVER_NAME" "case.params"
)
