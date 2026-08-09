#!/bin/sh
# Simulates a worker binary that fires the SessionStart hook (proving the
# spawn) but never fires UserPromptSubmit (proving a turn started). Used to
# reproduce the "delivered-but-unconfirmed" case: bootstrap_delivered is set
# before _bootstrap's retry loop exhausts, so the bootstrap file must survive.
set -e
DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../../../.agent/skills/agent-tabs" && pwd)
python3 "$DIR/agentctl.py" hook spawned
sleep 300
