#!/bin/sh
# Ordering probe, take 2. --force bypasses the readiness gates (which are
# currently wedged by the placeholder defect) but does NOT change _deliver's
# ordering, which is what we are measuring.
cd "/Users/acc/Library/CloudStorage/GoogleDrive-makarezp1@gmail.com/My Drive/Projects/CVviewer" || exit 1
export AGENT_TABS_RUNTIME=/tmp/probe-spike-run
export AGENT_TABS_RUN=probe-s1
export AGENT_TABS_VIEWER=none
CTL=.agent/skills/agent-tabs/agentctl.py

# clear the ZZZ we typed
i=0; while [ $i -lt 6 ]; do tmux send-keys -t @260 BSpace; i=$((i+1)); done
sleep 2

i=1
while [ $i -le 6 ]; do
  echo "--- iteration $i ---"
  "$CTL" send s1 "Reply with the single word OK. Run no commands." --force
  echo "  exit=$?"
  sleep 20
  i=$((i+1))
done
echo "DONE"
