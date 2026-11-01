#!/usr/bin/env bash
# Fixture tests for bin/roko-stratum1-bootstrap using a fake chronyc.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
subject="$here/../bin/roko-stratum1-bootstrap"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fake="$work/chronyc"
cat >"$fake" <<'FAKE'
#!/usr/bin/env bash
case "$1" in
  burst) [[ -z "${FAKE_BURST_FAIL:-}" ]] ;;
  waitsync) [[ -z "${FAKE_WAITSYNC_FAIL:-}" ]] ;;
  -c) if [[ "$*" == *tracking* ]]; then printf '%s\n' "${FAKE_TRACKING:-81060F1C,129.6.15.28,2}"; else cat "$FAKE_SOURCES"; fi ;;
  *) exit 2 ;;
esac
FAKE
chmod +x "$fake"

fails=0
run_case() {
  local name="$1" expect="$2" sources="$3"; shift 3
  printf '%s\n' "$sources" >"$work/sources.csv"
  local status=0 output
  output="$(env CHRONYC="$fake" FAKE_SOURCES="$work/sources.csv" ROKO_STRATUM1_SETTLE_S=0 "$@" "$subject" 2>&1)" || status=$?
  if [[ "$expect" == pass && $status -eq 0 ]] || [[ "$expect" == fail && $status -ne 0 ]]; then
    printf 'ok   %s\n' "$name"
  else
    printf 'FAIL %s (status=%s): %s\n' "$name" "$status" "$output"
    fails=$((fails + 1))
  fi
}

s2='^,*,198.51.100.7,2,10,377,86,-0.001146050,-0.001143582,0.027323734'
a='^,-,192.0.2.28,1,6,377,22,-0.000430347,-0.000430347,0.009163360'
b='^,-,192.0.2.29,1,6,377,20,0.001114392,0.001114392,0.008405159'
far='^,-,192.0.2.29,1,6,377,20,0.012000000,0.012000000,0.008405159'
stale='^,-,192.0.2.28,1,6,377,900,-0.000430347,-0.000430347,0.009163360'
unreached='^,?,192.0.2.28,1,6,0,-,0.000000000,0.000000000,0.000000000'

run_case "two fresh in-bound stratum-1 sources" pass "$(printf '%s\n' "$s2" "$a" "$b")"
run_case "one fresh source meets default minimum" pass "$(printf '%s\n' "$s2" "$a" "$far")"
run_case "minimum of two not met when one is far" fail "$(printf '%s\n' "$s2" "$a" "$far")" ROKO_STRATUM1_MIN_SOURCES=2
run_case "no stratum-1 source configured" fail "$s2"
run_case "only stale stratum-1 sample" fail "$(printf '%s\n' "$s2" "$stale")"
run_case "unreached stratum-1 source" fail "$(printf '%s\n' "$s2" "$unreached")"
run_case "burst refused (wrong user)" fail "$(printf '%s\n' "$s2" "$a")" FAKE_BURST_FAIL=1
run_case "host clock gate fails" fail "$(printf '%s\n' "$s2" "$a")" FAKE_WAITSYNC_FAIL=1
run_case "GPS refclock gives local stratum 1" pass "$(printf '%s\n' "$s2" "$a")" FAKE_TRACKING=47505300,GPS,1
run_case "stratum-1 agrees but clock follows stratum 3" fail "$(printf '%s\n' "$s2" "$a" "$b")" FAKE_TRACKING=A29FC87B,203.0.113.5,3
run_case "unparseable tracking output" fail "$(printf '%s\n' "$s2" "$a")" FAKE_TRACKING=garbage
run_case "local stratum limit can be raised" pass "$(printf '%s\n' "$s2" "$a")" FAKE_TRACKING=A29FC87B,203.0.113.5,4 ROKO_STRATUM1_MAX_LOCAL_STRATUM=4

output="$(env CHRONYC="$fake" FAKE_SOURCES="$work/sources.csv" ROKO_STRATUM1_SETTLE_S=0 "$subject" bogus 2>&1)" && { echo "FAIL unknown argument accepted"; fails=$((fails+1)); } || echo "ok   unknown argument rejected"

(( fails == 0 )) || { printf '%d case(s) failed\n' "$fails"; exit 1; }
printf 'stratum1 bootstrap: all cases passed\n'
