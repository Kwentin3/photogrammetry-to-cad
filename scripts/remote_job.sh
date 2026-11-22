#!/usr/bin/env bash
# Linux: one bounded command, no cloud/account operations and no cache removal.
# nohup bash remote_job.sh JOB_DIR TTL_SECONDS [--resume] -- COMMAND [ARG ...] \
#   >LAUNCH_LOG 2>&1 < /dev/null &
# Keep JOB_DIR and explicit Meshroom --cache/--save paths stable when resuming.
# 2023.3.0 batch needs --input even with --pipeline existing.mg. It has no resume
# switch; native successful chunks are reused unless --forceCompute is supplied.
# After an interrupted graph, inspect the old process/group before intentionally
# using native --forceStatus. This wrapper never adds force flags itself.
set -Eeuo pipefail
umask 077
die() { printf '%s\n' "$*" >&2; exit 1; }
[[ $# -ge 4 ]] || die 'Usage: remote_job.sh JOB_DIR TTL_SECONDS [--resume] -- COMMAND [ARG ...]'
job_dir=$1; ttl=$2; shift 2
resume=no
if [[ ${1:-} == --resume ]]; then resume=yes; shift; fi
[[ ${1:-} == -- ]] || die 'Expected -- before command'; shift
[[ $# -gt 0 ]] || die 'Missing command'
[[ $ttl =~ ^[1-9][0-9]*$ && ${#ttl} -le 5 ]] || die 'TTL must be integer seconds (1..14400)'
((ttl <= 14400)) || die 'TTL exceeds four hours; reserve transfer time separately'
for tool in flock timeout setsid sha256sum realpath ps; do
    command -v "$tool" >/dev/null || die "Missing tool: $tool"
done
process_python=${MESHROOM_PYTHON:-python3}
command -v "$process_python" >/dev/null || die "Missing process-owner Python: $process_python"
owner_helper=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/owned_process.py
[[ -f $owner_helper ]] || die 'Missing owned process-tree helper'
mkdir -p -- "$job_dir"
job_dir=$(realpath -- "$job_dir")
[[ $job_dir != / ]] || die 'Refusing root as job directory'
exec 9>"$job_dir/.job.lock"
flock -n 9 || { printf 'Job already owns %s\n' "$job_dir" >&2; exit 75; }
command_text=$(printf '%q ' "$@")
command_hash=$(printf '%s\n%s\n' "$PWD" "$command_text" | sha256sum)
command_hash=${command_hash%% *}
if [[ -f $job_dir/command.sha256 ]]; then
    [[ $resume == yes ]] || die 'Job already exists; inspect status and use --resume explicitly'
    [[ $(cat "$job_dir/command.sha256") == "$command_hash" ]] || die 'Resume command/cwd changed; use a new job directory'
    [[ $(grep '^cleanup=' "$job_dir/status" 2>/dev/null) == 'cleanup=confirmed' ]] \
        || die 'Prior tree cleanup is unconfirmed; inspect owned processes before resuming'
    prior_log=$(grep '^log=' "$job_dir/status") || die 'Missing prior log; inspect before resuming'
    [[ $prior_log != *$'\n'* ]] || die 'Ambiguous prior log; inspect before resuming'
    prior_log=${prior_log#log=}
    prior_log=${prior_log##*/}
    [[ $prior_log == *.log && $prior_log != .log ]] || die 'Invalid prior log; inspect before resuming'
    prior_receipt=$job_dir/${prior_log%.log}.owned-process
    [[ $(grep '^cleanup=' "$prior_receipt" 2>/dev/null) == 'cleanup=confirmed' ]] \
        || die 'Prior owned-tree receipt is missing or unconfirmed; inspect before resuming'
    if grep -q '^state=succeeded$' "$job_dir/status" 2>/dev/null; then
        printf 'Existing successful job reused: %s\n' "$job_dir"; exit 0
    fi
    # A dead parent may have left an orphan command; verify its own live group.
    if [[ -f $job_dir/process_group ]]; then
        old_group=$(cat "$job_dir/process_group")
        [[ $old_group =~ ^[1-9][0-9]*$ ]] || die 'Invalid stored process group'
        if kill -0 -- "-$old_group" 2>/dev/null; then
            die "Prior process group $old_group still exists; inspect before resuming"
        fi
    fi
else
    [[ $resume == no ]] || die 'No existing job to resume'
    [[ ! -f $job_dir/status ]] || die 'Unbound status exists; inspect before starting'
    printf '%s\n' "$command_hash" >"$job_dir/command.sha256"
    printf 'cwd=%q\ncommand=%s\n' "$PWD" "$command_text" >"$job_dir/command.txt"
fi
attempt=$(date -u +%Y%m%dT%H%M%S)-$$
started=$(date -u +%FT%TZ)
log=$job_dir/$attempt.log
owned_receipt=$job_dir/$attempt.owned-process
sha256sum "$owner_helper" >"$job_dir/$attempt.owned-helper.sha256"
child=''; cleanup=not_started
write_status() {
    printf 'state=%s\nexit_code=%s\nstarted_utc=%s\nupdated_utc=%s\nttl_seconds=%s\nrunner_pid=%s\nprocess_group=%s\ncleanup=%s\nlog=%s\n' \
        "$1" "$2" "$started" "$(date -u +%FT%TZ)" "$ttl" "$$" "${child:-}" "$cleanup" "$log" \
        >"$job_dir/status.tmp"
    mv -- "$job_dir/status.tmp" "$job_dir/status"
}
group_live() {
    # Zombies have terminated and cannot be killed; their parent must reap them.
    ps -eo pgid=,stat= | awk -v group="$child" '$1 == group && $2 !~ /^Z/ {found=1} END {exit !found}'
}
clean_group() {
    [[ -n $child ]] || return 0
    if group_live; then
        kill -TERM -- "-$child" 2>/dev/null || true
        for ((i=0; i<25; i++)); do group_live || break; sleep 1; done
        group_live && kill -KILL -- "-$child" 2>/dev/null || true
        for ((i=0; i<5; i++)); do group_live || break; sleep 1; done
    fi
    if group_live; then cleanup=unknown; return 1; fi
    cleanup=confirmed
}
finish() {
    local rc=$? state=failed
    trap - EXIT TERM INT
    clean_group || rc=125
    if [[ -n $child ]]; then wait "$child" 2>/dev/null || true; fi
    if [[ -n $child ]] && ! grep -qx 'cleanup=confirmed' "$owned_receipt" 2>/dev/null; then
        cleanup=unknown; rc=125
    fi
    if [[ $rc == 0 ]]; then state=succeeded
    elif [[ $rc == 124 ]]; then state=timed_out
    elif [[ $rc == 137 ]]; then state=killed; fi
    if [[ $rc == 130 || $rc == 143 ]]; then state=cancelled; fi
    [[ $cleanup != unknown ]] || state=cleanup_unknown
    write_status "$state" "$rc"
    exit "$rc"
}
trap finish EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
trap '' HUP
write_status starting ''
# GNU timeout creates a separate process group; setsid also isolates it from SSH.
# The subreaper also owns native workers that start separate sessions.
setsid timeout --signal=TERM --kill-after=25s "${ttl}s" \
    "$process_python" "$owner_helper" --receipt "$owned_receipt" -- "$@" >"$log" 2>&1 9>&- &
child=$!
printf '%s\n' "$child" >"$job_dir/process_group.tmp"
mv -- "$job_dir/process_group.tmp" "$job_dir/process_group"
cleanup=pending
write_status running ''
set +e
wait "$child"
result=$?
set -e
exit "$result"
