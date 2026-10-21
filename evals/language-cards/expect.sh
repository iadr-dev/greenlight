# Shared by the language card checks: run a command, compare its exit status with what the card says, keep the score.
# Sourced, not run. A command that is not installed never counts as "failed as expected".

passes=0
failures=0
log="${TMPDIR:-/tmp}/card-check.log"

run_quietly() {
    status=0
    "$@" >"$log" 2>&1 || status=$?
}

expect_pass() {
    what=$1
    shift
    run_quietly "$@"
    if [ "$status" -eq 0 ]; then
        echo "ok    passes as expected: $what"
        passes=$((passes + 1))
    else
        echo "FAIL  expected to pass: $what ($*), exit $status"
        sed 's/^/      /' "$log" | tail -n 20
        failures=$((failures + 1))
    fi
}

expect_fail() {
    what=$1
    shift
    run_quietly "$@"
    if [ "$status" -eq 126 ] || [ "$status" -eq 127 ]; then
        echo "FAIL  not installed or not runnable: $what ($*), exit $status"
        failures=$((failures + 1))
    elif [ "$status" -eq 0 ]; then
        echo "FAIL  expected to fail: $what ($*)"
        failures=$((failures + 1))
    else
        echo "ok    fails as expected: $what (exit $status)"
        sed 's/^/      /' "$log" | grep -i -m 2 -E "error|warning|deprecat|violation|lint|format" || true
        passes=$((passes + 1))
    fi
}

report_and_exit() {
    echo "$passes as the card says, $failures not"
    [ "$failures" -eq 0 ]
}
