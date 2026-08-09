import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";
import { resolveProcessCommand, runProcess } from "../src/common/process-runner.js";

test("captures stdout and exit code", async () => {
  const result = await runProcess(process.execPath, ["-e", "console.log('hello')"], {
    cwd: process.cwd(),
    timeoutMs: 5_000
  });

  assert.equal(result.status, "ok");
  assert.equal(result.exitCode, 0);
  assert.match(result.stdout, /hello/);
});

test("marks timeout", async () => {
  const result = await runProcess(process.execPath, ["-e", "setTimeout(() => {}, 10000)"], {
    cwd: process.cwd(),
    timeoutMs: 50
  });

  assert.equal(result.status, "timeout");
});

test("missing binary returns unavailable", async () => {
  const result = await runProcess("definitely-not-a-real-integrated-agent-binary", ["--version"], {
    cwd: process.cwd(),
    timeoutMs: 5_000
  });

  assert.equal(result.status, "unavailable");
  assert.equal(result.exitCode, null);
});

test("resolves bundled Windows native CLIs without relying on inherited PATH", () => {
  const root = mkdtempSync(join(tmpdir(), "integrated-agent-native-"));
  try {
    const claude = join(root, "npm", "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe");
    mkdirSync(dirname(claude), { recursive: true });
    writeFileSync(claude, "");
    const resolved = resolveProcessCommand("claude", ["--version"], {
      platform: "win32",
      env: { APPDATA: root, Path: "" }
    });
    assert.equal(resolved.command, claude);
    assert.deepEqual(resolved.args, ["--version"]);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("temporary-file input avoids placing prompt text in adapter arguments and cleans up", async () => {
  const result = await runProcess(
    process.execPath,
    [
      "-e",
      "const fs=require('fs'); console.log(process.argv[1]); console.log(fs.readFileSync(process.argv[1], 'utf8'))",
      "{{PROMPT_FILE}}"
    ],
    {
      cwd: process.cwd(),
      timeoutMs: 5_000,
      input: "sensitive task brief",
      inputMode: "temporary_file"
    }
  );
  const [promptPath] = result.stdout.trim().split(/\r?\n/);
  assert.equal(result.status, "ok");
  assert.match(result.stdout, /sensitive task brief/);
  assert.equal(existsSync(promptPath), false);
});

test("temporary-file input is cleaned up after timeout", async () => {
  const result = await runProcess(
    process.execPath,
    [
      "-e",
      "const fs=require('fs'); fs.openSync(process.argv[1], 'r'); console.log(process.argv[1]); setTimeout(() => {}, 10000)",
      "{{PROMPT_FILE}}"
    ],
    {
      cwd: process.cwd(),
      timeoutMs: 500,
      input: "timeout-sensitive task brief",
      inputMode: "temporary_file"
    }
  );
  const [promptPath] = result.stdout.trim().split(/\r?\n/);
  assert.equal(result.status, "timeout");
  assert.ok(promptPath);
  for (let attempt = 0; attempt < 20 && existsSync(promptPath); attempt += 1) {
    await delay(25);
  }
  assert.equal(existsSync(promptPath), false);
});
