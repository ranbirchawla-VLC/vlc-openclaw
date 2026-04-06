#!/usr/bin/env bash
#
# scaffold.sh — Create NutriOS data directory structure for a new user.
#
# Usage:
#   NUTRIOS_USER=ranbir NUTRIOS_DATA_ROOT=/path/to/drive/NutriOS/users/ranbir bash scripts/scaffold.sh
#
# If NUTRIOS_DATA_ROOT is not set, defaults to:
#   ~/.nutrios/users/$NUTRIOS_USER

set -euo pipefail

USER="${NUTRIOS_USER:?Set NUTRIOS_USER to the username}"
ROOT="${NUTRIOS_DATA_ROOT:-$HOME/.nutrios/users/$USER}"

echo "Scaffolding NutriOS for user: $USER"
echo "Data root: $ROOT"

mkdir -p "$ROOT/day-patterns"
mkdir -p "$ROOT/cycles"
mkdir -p "$ROOT/logs"

# protocol.json — empty template
if [ ! -f "$ROOT/protocol.json" ]; then
  cat > "$ROOT/protocol.json" << 'EOF'
{
  "user": "",
  "treatment": {
    "current_medication": "",
    "brand": "",
    "current_dose_mg": 0,
    "dose_day_of_week": "",
    "dose_time": "",
    "titration_notes": "",
    "next_transition_plan": "",
    "planned_stop_date": "",
    "restart_notes": ""
  },
  "biometrics": {
    "start_weight_lbs": 0,
    "current_weight_lbs": 0,
    "lean_mass_lbs": 0,
    "target_weight_lbs": 0,
    "target_date": "",
    "long_term_goal": "",
    "whoop_tdee_kcal": 0,
    "start_date": "",
    "weigh_ins": []
  },
  "thyroid_medication": false,
  "cgm_active": false,
  "med_team_notes": []
}
EOF
  # Set user field
  sed -i "s/\"user\": \"\"/\"user\": \"$USER\"/" "$ROOT/protocol.json"
  echo "  Created protocol.json"
else
  echo "  protocol.json already exists, skipping"
fi

# day-patterns/active.json
if [ ! -f "$ROOT/day-patterns/active.json" ]; then
  cat > "$ROOT/day-patterns/active.json" << 'EOF'
{
  "active_pattern_file": ""
}
EOF
  echo "  Created day-patterns/active.json"
else
  echo "  day-patterns/active.json already exists, skipping"
fi

# recipes.json
if [ ! -f "$ROOT/recipes.json" ]; then
  cat > "$ROOT/recipes.json" << 'EOF'
{
  "recipes": []
}
EOF
  echo "  Created recipes.json"
else
  echo "  recipes.json already exists, skipping"
fi

# events.json
if [ ! -f "$ROOT/events.json" ]; then
  cat > "$ROOT/events.json" << 'EOF'
{
  "events": []
}
EOF
  echo "  Created events.json"
else
  echo "  events.json already exists, skipping"
fi

# cycles/active.json
if [ ! -f "$ROOT/cycles/active.json" ]; then
  cat > "$ROOT/cycles/active.json" << 'EOF'
{
  "active_cycle_file": ""
}
EOF
  echo "  Created cycles/active.json"
else
  echo "  cycles/active.json already exists, skipping"
fi

echo ""
echo "Done. Directory structure:"
find "$ROOT" -type f | sort | sed "s|$ROOT/|  |"
echo ""
echo "Next steps:"
echo "  1. Seed initial state (protocol, day-patterns, events, cycles, recipes)"
echo "  2. Add env vars to ~/.openclaw/.env"
echo "  3. Register Telegram channel"
echo "  4. Start the bot"
