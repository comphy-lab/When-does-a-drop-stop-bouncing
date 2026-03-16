#!/usr/bin/env bash

# Shared shell helpers for reading and editing `key=value` parameter files used
# by `runSimulation.sh` and `runParameterSweep.sh`.

get_param_value() {
  # Return the first non-comment value associated with `key`.
  local file="$1"
  local key="$2"

  awk -F= -v search_key="$key" '
    /^[[:space:]]*#/ { next }
    {
      line = $0
      sub(/[[:space:]]*#.*/, "", line)
      if (line !~ /=/) next
      split(line, parts, "=")
      current_key = parts[1]
      sub(/^[[:space:]]+/, "", current_key)
      sub(/[[:space:]]+$/, "", current_key)
      if (current_key != search_key) next
      value = substr(line, index(line, "=") + 1)
      sub(/^[[:space:]]+/, "", value)
      sub(/[[:space:]]+$/, "", value)
      if (value ~ /^".*"$/ || value ~ /^'\''.*'\''$/) {
        value = substr(value, 2, length(value) - 2)
      }
      print value
      exit
    }
  ' "$file"
}

set_param_in_file() {
  # Replace `key` in place when present, otherwise append a new assignment.
  local file="$1"
  local key="$2"
  local value="$3"

  if grep -Eq "^[[:space:]]*${key}[[:space:]]*=" "$file"; then
    awk -v search_key="$key" -v new_value="$value" '
      {
        if ($0 ~ "^[[:space:]]*" search_key "[[:space:]]*=") {
          print search_key "=" new_value
        } else {
          print
        }
      }
    ' "$file" > "${file}.tmp" && mv "${file}.tmp" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

require_param_value() {
  # Read a required parameter and fail loudly when it is missing.
  local file="$1"
  local key="$2"
  local value

  value="$(get_param_value "$file" "$key")"
  if [[ -z "$value" ]]; then
    echo "Missing required parameter '$key' in $file" >&2
    return 1
  fi
  printf '%s\n' "$value"
}
