import assert from "node:assert/strict";
import test from "node:test";
import { redactSecrets } from "../src/common/redaction.js";

test("redacts common secret shapes", () => {
  const input = "OPENAI_API_KEY=sk-test SECRET_TOKEN=abc123 password: hunter2";
  const output = redactSecrets(input);
  assert.equal(output.includes("sk-test"), false);
  assert.equal(output.includes("abc123"), false);
  assert.equal(output.includes("hunter2"), false);
  assert.match(output, /\[REDACTED\]/);
});
