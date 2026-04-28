// emit-schemas.js; write tools.schema.json from the canonical tool-schemas.js manifest.
//
// Usage: node scripts/emit-schemas.js
// Or via npm:  npm run build:schemas
//
// Output: plugins/nutriosv2-tools/tools.schema.json
// Shape:  { "tools": [{ "name", "description", "inputSchema" }, ...] }
//
// Field translation: parameters (plugin) -> inputSchema (consumer).
// _script and _spawn are internal fields; stripped from output.

import { writeFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { TOOLS } from "../tool-schemas.js";

const pluginDir = dirname(dirname(fileURLToPath(import.meta.url)));

const output = {
  tools: TOOLS.map(({ name, description, parameters }) => ({
    name,
    description,
    inputSchema: parameters,
  })),
};

const outPath = join(pluginDir, "tools.schema.json");
writeFileSync(outPath, JSON.stringify(output, null, 2) + "\n");
console.log(`Wrote ${output.tools.length} tools to tools.schema.json`);
for (const t of output.tools) {
  console.log(`  ${t.name}`);
}
