// Tool schema definitions for the gtd-tools plugin.
// Each entry: { _script, _spawn, name, description, parameters }.
// _script paths are relative to gtd-workspace/scripts/ (the plugin SCRIPTS base).
// _script and _spawn are internal fields used by index.js to build execute functions.
// The emit script strips them and renames parameters -> inputSchema.
export const TOOLS = [
  // ---------------------------------------------------------------------------
  // Calendar tools
  // ---------------------------------------------------------------------------
  {
    _script: "calendar/get_events.py",
    _spawn: "argv",
    name: "list_events",
    description: "List upcoming Google Calendar events. Returns {ok: true, data: {events: [{id, summary, start, end, attendees, location, description, html_link}]}}.",
    parameters: {
      type: "object",
      properties: {
        calendar_id: {
          type: "string",
          description: "Calendar ID to query (default: 'primary')",
        },
        time_min: {
          type: "string",
          description: "Start of time range, ISO 8601 (default: now)",
        },
        time_max: {
          type: "string",
          description: "End of time range, ISO 8601 (default: now + 7 days)",
        },
        max_results: {
          type: "integer",
          description: "Maximum number of events to return (default: 25)",
        },
      },
      required: [],
    },
  },
  {
    _script: "calendar/get_event.py",
    _spawn: "argv",
    name: "get_event",
    description: "Get a single Google Calendar event by ID. Returns {ok: true, data: {event: {...}}} with the full event object.",
    parameters: {
      type: "object",
      properties: {
        event_id: {
          type: "string",
          description: "Google Calendar event ID",
        },
        calendar_id: {
          type: "string",
          description: "Calendar ID containing the event (default: 'primary')",
        },
      },
      required: ["event_id"],
    },
  },
  // ---------------------------------------------------------------------------
  // GTD tools
  // ---------------------------------------------------------------------------
  {
    _script: "gtd/capture.py",
    _spawn: "argv",
    name: "capture_gtd",
    description: "Capture a GTD record (task, idea, or parking_lot). Returns {ok: true, data: {id, record_type}} on success.",
    parameters: {
      type: "object",
      properties: {
        record: {
          type: "object",
          description: "The assembled GTD record. Must include record_type and required fields for that type.",
        },
      },
      required: ["record"],
    },
  },
  {
    _script: "gtd/query_tasks.py",
    _spawn: "argv",
    name: "query_tasks",
    description: "Query GTD tasks with optional filters. Returns {ok: true, data: {items, total_count, truncated}}.",
    parameters: {
      type: "object",
      properties: {
        context: {
          type: "string",
          description: "Filter by context (e.g. '@phone', '@computer')",
        },
        due_date_before: {
          type: "string",
          description: "Return tasks with due_date <= this ISO date (YYYY-MM-DD)",
        },
        due_date_after: {
          type: "string",
          description: "Return tasks with due_date >= this ISO date (YYYY-MM-DD)",
        },
        has_waiting_for: {
          type: "boolean",
          description: "true: only tasks with waiting_for set; false: only tasks without",
        },
        limit: {
          type: "integer",
          description: "Maximum number of items to return (default: 10; max: 25)",
        },
      },
      required: [],
    },
  },
  {
    _script: "gtd/query_ideas.py",
    _spawn: "argv",
    name: "query_ideas",
    description: "Query GTD ideas. Returns {ok: true, data: {items, total_count, truncated}}.",
    parameters: {
      type: "object",
      properties: {
        limit: {
          type: "integer",
          description: "Maximum number of items to return (default: 10; max: 25)",
        },
      },
      required: [],
    },
  },
  {
    _script: "gtd/query_parking_lot.py",
    _spawn: "argv",
    name: "query_parking_lot",
    description: "Query GTD parking lot items. Returns {ok: true, data: {items, total_count, truncated}}.",
    parameters: {
      type: "object",
      properties: {
        limit: {
          type: "integer",
          description: "Maximum number of items to return (default: 10; max: 25)",
        },
      },
      required: [],
    },
  },
  {
    _script: "gtd/review.py",
    _spawn: "argv",
    name: "review_gtd",
    description: "Run a structured GTD review scan. Returns {ok: true, data: {items, total_count, truncated, review_available, note}}. review_available is false until review semantics are fully designed.",
    parameters: {
      type: "object",
      properties: {
        limit: {
          type: "integer",
          description: "Maximum number of items to return (default: 10; max: 25)",
        },
      },
      required: [],
    },
  },
  {
    _script: "gtd/delegation.py",
    _spawn: "argv",
    name: "delegation",
    description: "Query waiting-for tasks grouped by person. Returns {ok: true, data: {groups: [{person, count, items}], total_items, truncated}}.",
    parameters: {
      type: "object",
      properties: {
        person: {
          type: "string",
          description: "Filter to a specific person's waiting-for items (omit for all persons)",
        },
        limit: {
          type: "integer",
          description: "Maximum items per person group (default: 10; max: 25)",
        },
      },
      required: [],
    },
  },
];
