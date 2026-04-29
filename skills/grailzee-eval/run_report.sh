#!/bin/zsh
set -e
cd /Users/ranbirchawla/.openclaw/workspace/skills/grailzee-eval
GDRIVE="/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive/GrailzeeData/reports"

REPORT="$1"
if [ -z "$REPORT" ]; then
  echo "Usage: $0 <report-filename>"
  exit 1
fi

python3 scripts/report_pipeline.py "${GDRIVE}/${REPORT}"
