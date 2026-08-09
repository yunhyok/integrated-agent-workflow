import assert from "node:assert/strict";
import test from "node:test";
import {
  getLMStudioConfig,
  normalizeLMStudioBaseUrl,
  toOpenAIBaseUrl
} from "../src/common/lmstudio-config.js";
import { listLMStudioModels } from "../src/tools/lmstudio-models.js";

test("normalizes and validates LM Studio base URLs", () => {
  assert.equal(normalizeLMStudioBaseUrl("192.0.2.10:1234"), "http://192.0.2.10:1234");
  assert.equal(normalizeLMStudioBaseUrl("http://192.0.2.10:1234/v1/"), "http://192.0.2.10:1234");
  assert.equal(toOpenAIBaseUrl("http://192.0.2.10:1234"), "http://192.0.2.10:1234/v1");
  assert.throws(() => normalizeLMStudioBaseUrl("file:///tmp/server"), /http or https/);
  assert.throws(() => normalizeLMStudioBaseUrl("http://user:secret@localhost:1234"), /credentials/);
  assert.throws(() => normalizeLMStudioBaseUrl("http://localhost:1234?token=secret"), /query string/);
});

test("reads the registered LM Studio endpoint, model, and context from environment", () => {
  const config = getLMStudioConfig({
    LMSTUDIO_BASE_URL: "192.0.2.10:1234/v1",
    LMSTUDIO_MODEL: "example-model@q4_gguf",
    LMSTUDIO_CONTEXT_WINDOW: "32768"
  });

  assert.equal(config.baseUrl, "http://192.0.2.10:1234");
  assert.equal(config.openAIBaseUrl, "http://192.0.2.10:1234/v1");
  assert.equal(config.model, "example-model@q4_gguf");
  assert.equal(config.contextWindow, 32768);
});

test("discovers selectable LLMs and preserves loaded instance IDs", async () => {
  const config = getLMStudioConfig({
    LMSTUDIO_BASE_URL: "http://127.0.0.1:1234",
    LMSTUDIO_MODEL: "example-model@q4_gguf"
  });
  const fetchImpl = async (input: string | URL) => {
    const url = String(input);
    if (url.endsWith("/api/v1/models")) {
      return Response.json({
        models: [
          {
            type: "llm",
            key: "example-model@q4_k_m",
            display_name: "Example Model",
            params_string: "31B",
            quantization: { name: "Q4_K_M" },
            loaded_instances: [{ id: "example-model@q4_gguf" }],
            max_context_length: 32768,
            capabilities: { trained_for_tool_use: true, vision: false }
          },
          {
            type: "embedding",
            key: "text-embedding-model",
            display_name: "Embedding",
            loaded_instances: []
          }
        ]
      });
    }
    return Response.json({
      object: "list",
      data: [
        { id: "example-model@q4_gguf" },
        { id: "example-model@q4_k_m" },
        { id: "text-embedding-model" }
      ]
    });
  };

  const result = await listLMStudioModels({ config, fetchImpl });
  assert.equal(result.status, "available");
  assert.equal(result.configuredModelAvailable, true);
  assert.deepEqual(result.models.map((model) => model.id), [
    "example-model@q4_gguf",
    "example-model@q4_k_m"
  ]);
  assert.deepEqual(result.models[0], {
    id: "example-model@q4_gguf",
    key: "example-model@q4_k_m",
    displayName: "Example Model",
    loaded: true,
    isDefault: true,
    params: "31B",
    quantization: "Q4_K_M",
    maxContextLength: 32768,
    trainedForToolUse: true,
    vision: false
  });
});

test("returns unavailable without leaking failed response bodies", async () => {
  const config = getLMStudioConfig({ LMSTUDIO_BASE_URL: "http://127.0.0.1:1234" });
  const result = await listLMStudioModels({
    config,
    fetchImpl: async () => new Response("private upstream body", { status: 503, statusText: "Unavailable" })
  });

  assert.equal(result.status, "unavailable");
  assert.equal(result.models.length, 0);
  assert.match(result.errorMessage ?? "", /HTTP 503 Unavailable/);
  assert.equal(JSON.stringify(result).includes("private upstream body"), false);
});

test("does not leak malformed successful response bodies", async () => {
  const config = getLMStudioConfig({ LMSTUDIO_BASE_URL: "http://127.0.0.1:1234" });
  const result = await listLMStudioModels({
    config,
    fetchImpl: async () => new Response("private upstream body with SECRET-XYZ", { status: 200 })
  });

  assert.equal(result.status, "unavailable");
  assert.match(result.errorMessage ?? "", /Invalid JSON response/);
  assert.equal(JSON.stringify(result).includes("private upstream body"), false);
  assert.equal(JSON.stringify(result).includes("SECRET-XYZ"), false);
});

test("normalizes malformed native metadata without throwing", async () => {
  const config = getLMStudioConfig({ LMSTUDIO_BASE_URL: "http://127.0.0.1:1234" });
  const result = await listLMStudioModels({
    config,
    fetchImpl: async (input) => String(input).includes("/api/v1/")
      ? Response.json({
          models: [{
            type: "llm",
            key: "safe-model",
            loaded_instances: { id: "not-an-array" },
            variants: "not-an-array"
          }]
        })
      : Response.json({ data: [{ id: "safe-model" }] })
  });

  assert.equal(result.status, "available");
  assert.deepEqual(result.models.map((model) => model.id), ["safe-model"]);
  assert.equal(result.models[0].loaded, false);
  assert.match(result.warnings.join("\n"), /invalid loaded_instances metadata/);
  assert.match(result.warnings.join("\n"), /invalid variants metadata/);
});

test("returns unavailable when both successful endpoints use unknown schemas", async () => {
  const config = getLMStudioConfig({ LMSTUDIO_BASE_URL: "http://127.0.0.1:1234" });
  const result = await listLMStudioModels({
    config,
    fetchImpl: async () => Response.json({ unexpected: true })
  });

  assert.equal(result.status, "unavailable");
  assert.equal(result.models.length, 0);
  assert.match(result.errorMessage ?? "", /unexpected schema/);
});
