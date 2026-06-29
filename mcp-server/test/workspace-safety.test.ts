import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { evaluateWorkspaceSafety, getWorkspaceState } from "../src/common/workspace-safety.js";

test("isolated_write is disallowed for a non-isolated temp directory", () => {
  const tempDir = mkdtempSync(join(tmpdir(), "integrated-agent-workspace-"));
  try {
    const safety = evaluateWorkspaceSafety(tempDir, "isolated_write");

    assert.equal(safety.allowed, false);
    assert.equal(safety.status, "unsafe_request");
    assert.equal(safety.workspace.gitRepository, false);
    assert.equal(safety.workspace.isolatedWriteAvailable, false);
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

test("current workspace state returns booleans without throwing", () => {
  const workspace = getWorkspaceState(process.cwd());

  assert.equal(typeof workspace.gitRepository, "boolean");
  assert.equal(typeof workspace.dirty, "boolean");
  assert.equal(typeof workspace.linkedWorktree, "boolean");
  assert.equal(typeof workspace.isolatedWriteAvailable, "boolean");
});
