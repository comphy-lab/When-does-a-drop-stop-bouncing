#!/usr/bin/env bash
# Generate a Cartesian sweep of case parameters and launch each case through
# `runSimulation.sh`.
#
# The sweep specification lives in `sweep.params` and expands each `SWEEP_*`
# key into a product set. Case numbering is assigned sequentially from
# `CASE_START` to `CASE_END`.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT_DIR/src-local/params.sh"

usage() {
  cat <<'EOF'
Usage: bash runParameterSweep.sh [--dry-run] [sweep-params-file]

Generate parameter combinations from sweep.params and launch each case
through runSimulation.sh.

Expected keys in sweep params:
  CASE_START, CASE_END
  SWEEP_We, SWEEP_Ohd, SWEEP_Ohs, SWEEP_Bo, SWEEP_Ldomain

Optional sweep dimensions:
  SWEEP_MAXlevel, SWEEP_tmax
EOF
}

DRY_RUN=0
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

SWEEP_FILE="${1:-$ROOT_DIR/sweep.params}"
if [[ ! -f "$SWEEP_FILE" ]]; then
  echo "Sweep file not found: $SWEEP_FILE" >&2
  exit 1
fi

CASE_START="$(require_param_value "$SWEEP_FILE" "CASE_START")"
CASE_END="$(require_param_value "$SWEEP_FILE" "CASE_END")"
if [[ ! "$CASE_START" =~ ^[0-9]+$ || ! "$CASE_END" =~ ^[0-9]+$ || "$CASE_END" -lt "$CASE_START" ]]; then
  echo "CASE_START and CASE_END must be non-negative integers with CASE_END >= CASE_START" >&2
  exit 1
fi

load_sweep_values() {
  # Read one whitespace-delimited sweep dimension from the active sweep file.
  local key="$1"
  local raw
  raw="$(get_param_value "$SWEEP_FILE" "$key")"
  if [[ -z "$raw" ]]; then
    echo "Missing $key in $SWEEP_FILE" >&2
    exit 1
  fi
  local -a values=()
  read -r -a values <<< "$raw"
  if [[ "${#values[@]}" -eq 0 ]]; then
    echo "No values provided for $key in $SWEEP_FILE" >&2
    exit 1
  fi
  printf '%s\n' "${values[@]}"
}

load_sweep_array() {
  # Populate a named bash array from one sweep dimension.
  local array_name="$1"
  local key="$2"
  local value
  eval "$array_name=()"
  while IFS= read -r value; do
    eval "$array_name+=(\"\$value\")"
  done < <(load_sweep_values "$key")
}

load_sweep_array sweep_we "SWEEP_We"
load_sweep_array sweep_ohd "SWEEP_Ohd"
load_sweep_array sweep_ohs "SWEEP_Ohs"
load_sweep_array sweep_bo "SWEEP_Bo"
load_sweep_array sweep_ldomain "SWEEP_Ldomain"

read_optional_sweep() {
  # Fall back to the corresponding value in `default.params` when a sweep
  # dimension is omitted.
  local key="$1"
  local fallback="$2"
  local raw
  raw="$(get_param_value "$SWEEP_FILE" "$key")"
  if [[ -z "$raw" ]]; then
    printf '%s\n' "$fallback"
  else
    printf '%s\n' "$raw"
  fi
}

read -r -a sweep_maxlevel <<< "$(read_optional_sweep "SWEEP_MAXlevel" "$(get_param_value "$ROOT_DIR/default.params" "MAXlevel")")"
read -r -a sweep_tmax <<< "$(read_optional_sweep "SWEEP_tmax" "$(get_param_value "$ROOT_DIR/default.params" "tmax")")"

expected_count=$(( ${#sweep_we[@]} * ${#sweep_ohd[@]} * ${#sweep_ohs[@]} * ${#sweep_bo[@]} * ${#sweep_ldomain[@]} * ${#sweep_maxlevel[@]} * ${#sweep_tmax[@]} ))
case_span=$(( CASE_END - CASE_START + 1 ))

if [[ "$expected_count" -ne "$case_span" ]]; then
  echo "CASE_START/CASE_END span ($case_span) does not match generated combinations ($expected_count)" >&2
  exit 1
fi

QCC_BIN="$(get_param_value "$SWEEP_FILE" "QCC")"
QCC_BIN="${QCC_BIN:-$(get_param_value "$ROOT_DIR/default.params" "QCC")}"
QCCFLAGS_RAW="$(get_param_value "$SWEEP_FILE" "QCCFLAGS")"
QCCFLAGS_RAW="${QCCFLAGS_RAW:-$(get_param_value "$ROOT_DIR/default.params" "QCCFLAGS")}"
OMP_THREADS="$(get_param_value "$SWEEP_FILE" "OMP_NUM_THREADS")"
OMP_THREADS="${OMP_THREADS:-$(get_param_value "$ROOT_DIR/default.params" "OMP_NUM_THREADS")}"

case_no="$CASE_START"
# Iterate over the full Cartesian product and materialize a temporary case
# parameter file for each point in the sweep.
for we in "${sweep_we[@]}"; do
  for ohd in "${sweep_ohd[@]}"; do
    for ohs in "${sweep_ohs[@]}"; do
      for bo in "${sweep_bo[@]}"; do
        for ldomain in "${sweep_ldomain[@]}"; do
          for maxlevel in "${sweep_maxlevel[@]}"; do
            for tmax in "${sweep_tmax[@]}"; do
              temp_params="$(mktemp "$ROOT_DIR/.case-${case_no}-XXXX.params")"
              cp "$ROOT_DIR/default.params" "$temp_params"
              set_param_in_file "$temp_params" "CaseNo" "$case_no"
              set_param_in_file "$temp_params" "We" "$we"
              set_param_in_file "$temp_params" "Ohd" "$ohd"
              set_param_in_file "$temp_params" "Ohs" "$ohs"
              set_param_in_file "$temp_params" "Bo" "$bo"
              set_param_in_file "$temp_params" "Ldomain" "$ldomain"
              set_param_in_file "$temp_params" "MAXlevel" "$maxlevel"
              set_param_in_file "$temp_params" "tmax" "$tmax"
              set_param_in_file "$temp_params" "QCC" "$QCC_BIN"
              set_param_in_file "$temp_params" "QCCFLAGS" "$QCCFLAGS_RAW"
              set_param_in_file "$temp_params" "OMP_NUM_THREADS" "$OMP_THREADS"

              echo "CaseNo=$case_no We=$we Ohd=$ohd Ohs=$ohs Bo=$bo Ldomain=$ldomain MAXlevel=$maxlevel tmax=$tmax"
              if [[ "$DRY_RUN" -eq 0 ]]; then
                bash "$ROOT_DIR/runSimulation.sh" "$temp_params"
              fi
              rm -f "$temp_params"
              case_no=$((case_no + 1))
            done
          done
        done
      done
    done
  done
done
