#!/bin/sh
# check.sh --selftest (offline)  |  check.sh --run [CASE ...] [--n N] (needs the live room; see .env.example)
exec python3 "$(dirname "$0")/tools/check.py" "$@"
