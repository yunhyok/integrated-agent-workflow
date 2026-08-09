import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { writeRunArtifact } from "../src/common/run-artifacts.js";

test("writeRunArtifact redacts secrets under the run artifact directory", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "integrated-agent-artifact-"));
  try {
    const logPath = writeRunArtifact(tempDir, "claude", {
      stdout: "generated with sk-test12345",
      token: "sk-test67890"
    });
    const body = readFileSync(logPath, "utf8");

    assert.match(logPath, /[\\/]\.codex[\\/]multi-agent[\\/]runs[\\/]/);
    assert.match(logPath, /result\.json$/);
    assert.equal(body.includes("sk-test12345"), false);
    assert.equal(body.includes("sk-test67890"), false);
    assert.match(body, /\[REDACTED\]/);
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});
