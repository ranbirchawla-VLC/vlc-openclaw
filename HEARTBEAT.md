# HEARTBEAT.md

## Checks

### OTel Collector Health
Run: `launchctl list | grep otelcol`
- If exit code is `0` → healthy, do nothing
- If `-` or missing → collector is down, alert Ranbir:
  "⚠️ OTel collector is down — run: launchctl start ai.openclaw.otelcol"
- Check at most once per heartbeat cycle, skip if checked in last 2 hours

## Notes
- Only alert if something is actually wrong
- Don't check if it's between 23:00–08:00 MDT unless critical
