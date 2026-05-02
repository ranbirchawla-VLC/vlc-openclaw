// Tool schema definitions for the gtd-tools plugin.
// Each entry: { _script, _spawn, name, description, parameters }.
// _script and _spawn are internal fields used by index.js to build execute functions.
// The emit script strips them and renames parameters -> inputSchema.
export const TOOLS = [
  {
    _script: "get_events.py",
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
    _script: "get_event.py",
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
];
