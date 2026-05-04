#!/bin/bash
# Pipeline runner - processes reports in chronological order
set -e

REPORTS_DIR="/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive/GrailzeeData/reports"

echo "=== Processing March W1 ==="
python3 scripts/report_pipeline.py "$REPORTS_DIR/Grailzee Pro Bi-Weekly Report - March W1.xlsx"

echo "=== Processing March W2 ==="
python3 scripts/report_pipeline.py "$REPORTS_DIR/Grailzee Pro Bi-Weekly Report - March W2.xlsx"

echo "=== Processing April W1 ==="
python3 scripts/report_pipeline.py "$REPORTS_DIR/Grailzee Pro Bi-Weekly Report - April W1.xlsx"
