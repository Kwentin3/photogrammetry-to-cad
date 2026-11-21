#!/usr/bin/env bash
# Run independently from the CPU/GPU job:
#   nohup bash rental_deadline.sh DEADLINE_UTC_EPOCH STATE_DIR >WATCHDOG_LOG 2>&1 < /dev/null &
# First save instance ID, creation time and this absolute deadline OFF NODE/outside
# Git. Deadline must be at most creation+4h; leave time to retrieve and verify data.
# This script can validate remaining time, not the off-node creation record.
#
# STOP only: disk/data remain and storage charges continue. No destroy or account
# key is used. A dead host/container or failed API prevents this watchdog working;
# it is not an external fail-safe or a guarantee of total rental spend.
#
# Endpoint checked against official vast-cli v1.11.2, 2026-11-21:
# https://github.com/vast-ai/vast-cli/blob/v1.11.2/vastai/api/instances.py
# stop_instance: PUT /instances/{id}/ with {"state":"stopped"}.
# https://github.com/vast-ai/vast-cli/blob/v1.11.2/vastai/api/client.py
# VastClient._build_url prefixes /api/v0; default origin https://console.vast.ai.
# Per-instance key usage is documented in:
# https://docs.vast.ai/guides/instances/docker-environment.md
set +x
set -Eeuo pipefail
umask 077
die() { printf '%s\n' "$*" >&2; exit 1; }
[[ $# == 2 ]] || die 'Usage: rental_deadline.sh DEADLINE_UTC_EPOCH STATE_DIR'
deadline=$1; state_dir=$2
[[ $deadline =~ ^[1-9][0-9]{9,10}$ ]] || die 'Invalid absolute UTC epoch deadline'
[[ ${CONTAINER_ID:-} =~ ^[1-9][0-9]{0,14}$ ]] || die 'Missing/invalid CONTAINER_ID'
# Reject configuration/header injection; never print the value or put it in argv.
[[ ${CONTAINER_API_KEY:-} =~ ^[A-Za-z0-9._~+/=-]+$ ]] || die 'Missing/invalid per-instance CONTAINER_API_KEY'
for tool in curl grep flock date sleep realpath; do
    command -v "$tool" >/dev/null || die "Missing tool: $tool"
done
now=$(date -u +%s)
((deadline - now <= 14400)) || die 'Deadline exceeds four hours from now'
mkdir -p -- "$state_dir"
state_dir=$(realpath -- "$state_dir")
[[ $state_dir != / ]] || die 'Refusing root as watchdog state directory'
exec 9>"$state_dir/.deadline.lock"
flock -n 9 || { printf 'Watchdog already owns this state directory\n' >&2; exit 75; }
binding=$(printf 'instance_id=%s\ndeadline_epoch=%s' "$CONTAINER_ID" "$deadline")
if [[ -f $state_dir/binding ]]; then
    [[ $(cat "$state_dir/binding") == "$binding" ]] || die 'Existing watchdog binding differs; refusing to extend/replace it'
else
    printf '%s\n' "$binding" >"$state_dir/binding.tmp"
    mv -- "$state_dir/binding.tmp" "$state_dir/binding"
fi
write_state() {
    printf 'state=%s\ninstance_id=%s\ndeadline_epoch=%s\nupdated_utc=%s\nwatchdog_pid=%s\n' \
        "$1" "$CONTAINER_ID" "$deadline" "$(date -u +%FT%TZ)" "$$" >"$state_dir/status.tmp"
    mv -- "$state_dir/status.tmp" "$state_dir/status"
}
trap '' HUP
write_state waiting
printf 'watchdog_armed=true deadline_epoch=%s\n' "$deadline"
# Recheck the absolute clock after bounded sleeps; an SSH disconnect has no role.
while (( (now=$(date -u +%s)) < deadline )); do
    remaining=$((deadline - now))
    ((remaining <= 30)) || remaining=30
    sleep "$remaining"
done
write_state requesting_stop
for attempt in 1 2 3; do
    # --disable must be first: ignore .curlrc (which could enable verbose output).
    # Credentials are delivered by a Bash builtin to curl config on stdin. No
    # redirects, insecure TLS, generic VAST_API_KEY fallback or response logging.
    response=''; transport_ok=false
    if response=$(printf 'header = "Authorization: Bearer %s"\n' "$CONTAINER_API_KEY" | \
        curl --disable --config - --silent --fail --connect-timeout 10 --max-time 30 \
            --proto '=https' --request PUT --header 'Content-Type: application/json' \
            --data '{"state":"stopped"}' \
            "https://console.vast.ai/api/v0/instances/$CONTAINER_ID/" 2>/dev/null); then
        transport_ok=true
    fi
    success=false
    # The native API returns a simple object. This conservative field check is
    # NOT a full JSON validator. Reject explicit false/error fields and require
    # object delimiters plus quoted success:true after a successful HTTP response.
    # Off-node status polling remains the authority for actual stopped state.
    if [[ $transport_ok == true && $response =~ ^[[:space:]]*\{ && $response =~ \}[[:space:]]*$ ]] \
        && printf '%s' "$response" | grep -Eq '"success"[[:space:]]*:[[:space:]]*true([[:space:],}])' \
        && ! printf '%s' "$response" | grep -Eq '"success"[[:space:]]*:[[:space:]]*false|"error"[[:space:]]*:'; then
        success=true
    fi
    unset response
    printf 'attempt=%s stop_request_success=%s\n' "$attempt" "$success"
    if [[ $success == true ]]; then
        # An accepted request is not proof of terminal state; verify off node.
        write_state stop_accepted
        exit 0
    fi
    [[ $attempt == 3 ]] || sleep 2
done
write_state stop_unconfirmed
exit 1
