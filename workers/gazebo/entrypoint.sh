#!/usr/bin/env bash
set -e
source /opt/ros/jazzy/setup.bash
export PYTHONPATH="/opt/clavius/backend${PYTHONPATH:+:$PYTHONPATH}"
if [[ -z "${CLAVIUS_GAZEBO_TOKEN:-}" ]]; then
  echo 'Set CLAVIUS_GAZEBO_TOKEN before starting the network worker.' >&2
  exit 2
fi
/opt/clavius-venv/bin/python -c 'from clavius.gazebo_runtime import runtime_capabilities; import json,sys; result=runtime_capabilities(); print(json.dumps(result,indent=2)); sys.exit(0 if result["runtime_available"] else 2)'
exec "$@"
