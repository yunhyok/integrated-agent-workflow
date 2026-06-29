import assert from "node:assert/strict";
import test from "node:test";
import { listToolNames } from "../src/server.js";

test("server registers v1 tools", () => {
  assert.deepEqual(listToolNames().sort(), ["doctor", "run_agent", "run_panel", "summarize_results"]);
});
