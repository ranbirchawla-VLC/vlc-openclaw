// Tool schema definitions for the gtd-tools plugin.
// Each entry: { _script, _spawn, name, description, parameters }.
// _script paths are relative to gtd-workspace/scripts/ (the plugin SCRIPTS base).
// _script and _spawn are internal fields used by index.js to build execute functions.
// The emit script strips them and renames parameters -> inputSchema.
export const TOOLS = [
  // ---------------------------------------------------------------------------
  // Dispatcher -- call first on every turn
  // ---------------------------------------------------------------------------
  {
    _script: "turn_state.py",
    _spawn: "stdin",
    name: "trina_dispatch",
    description: "Classify intent from the verbatim user message and return the matching capability prompt. Call first on every turn before any other tool. Returns {ok: true, data: {intent, capability_prompt}}.",
    parameters: {
      type: "object",
      properties: {
        user_message: {
          type: "string",
          description: "The verbatim user message, unmodified.",
        },
      },
      required: ["user_message"],
    },
  },
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
    name: "capture",
    description: "Capture a GTD record (task, idea, or parking_lot). Returns {ok: true, data: {captured: {id, ...}}} where captured contains type-specific fields. task: id, title, context, project, priority, waiting_for, due_date, notes, status, created_at, updated_at, last_reviewed, completed_at. idea: id, title, topic, content, status, created_at, updated_at, last_reviewed, completed_at. parking_lot: id, content, reason, status, created_at, updated_at, last_reviewed, completed_at. record_type, source, telegram_chat_id excluded.",
    parameters: {
      type: "object",
      properties: {
        user_id: {
          type: "string",
          description: "Sender's Telegram user ID. Read sender_id from the conversation metadata (untrusted).",
        },
        record: {
          type: "object",
          description: "The assembled GTD record. Must include record_type and required fields for that type.",
        },
      },
      required: ["user_id", "record"],
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
        user_id: {
          type: "string",
          description: "Sender's Telegram user ID. Read sender_id from the conversation metadata (untrusted).",
        },
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
      required: ["user_id"],
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
        user_id: {
          type: "string",
          description: "Sender's Telegram user ID. Read sender_id from the conversation metadata (untrusted).",
        },
        limit: {
          type: "integer",
          description: "Maximum number of items to return (default: 10; max: 25)",
        },
      },
      required: ["user_id"],
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
        user_id: {
          type: "string",
          description: "Sender's Telegram user ID. Read sender_id from the conversation metadata (untrusted).",
        },
        limit: {
          type: "integer",
          description: "Maximum number of items to return (default: 10; max: 25)",
        },
      },
      required: ["user_id"],
    },
  },
  {
    _script: "gtd/review.py",
    _spawn: "argv",
    name: "review",
    description: "Run a structured GTD review pass; stamp stale records per record type. Returns {ok: true, data: {reviewed_at: <iso>, by_type: {tasks: {items, total_count, truncated}, ideas: {items, total_count, truncated}, parking_lot: {items, total_count, truncated}}}}. On partial stamp failure: {ok: false, error: {code: \"storage_unavailable\", path: <failing-file>, ...}}.",
    parameters: {
      type: "object",
      properties: {
        user_id: {
          type: "string",
          description: "Sender's Telegram user ID. Read sender_id from the conversation metadata (untrusted).",
        },
        record_types: {
          type: "array",
          items: { type: "string", enum: ["tasks", "ideas", "parking_lot"] },
          description: "Record types to include in the review pass. Allowed values: 'tasks', 'ideas', 'parking_lot'. Default: all three. Omit to review all types.",
        },
        stale_for_days: {
          type: "integer",
          description: "Days before a record is considered stale (default: 7). Records not reviewed within this window are returned and stamped.",
        },
        limit_per_type: {
          type: "integer",
          description: "Maximum records to stamp per record type (default: 25; max: 25).",
        },
      },
      required: ["user_id"],
    },
  },
];
