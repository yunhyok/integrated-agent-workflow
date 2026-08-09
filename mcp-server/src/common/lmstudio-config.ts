export const DEFAULT_LMSTUDIO_BASE_URL = "http://127.0.0.1:1234";
export const LMSTUDIO_PROVIDER_ID = "lmstudio_remote";

export interface LMStudioConfig {
  baseUrl: string;
  openAIBaseUrl: string;
  model?: string;
  contextWindow?: number;
  apiToken?: string;
}

export function normalizeLMStudioBaseUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) throw new Error("LM Studio base URL must not be empty.");

  const withScheme = /^[a-z][a-z\d+.-]*:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;
  const url = new URL(withScheme);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("LM Studio base URL must use http or https.");
  }
  if (url.username || url.password) {
    throw new Error("LM Studio base URL must not contain credentials.");
  }
  if (url.search || url.hash) {
    throw new Error("LM Studio base URL must not contain a query string or fragment.");
  }

  let path = url.pathname.replace(/\/+$/, "");
  if (path.endsWith("/v1")) path = path.slice(0, -3);
  return `${url.origin}${path}`;
}

export function toOpenAIBaseUrl(baseUrl: string): string {
  return `${normalizeLMStudioBaseUrl(baseUrl)}/v1`;
}

function parseContextWindow(value: string | undefined): number | undefined {
  if (!value?.trim()) return undefined;
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    throw new Error("LMSTUDIO_CONTEXT_WINDOW must be a positive integer.");
  }
  return parsed;
}

export function getLMStudioConfig(env: NodeJS.ProcessEnv = process.env): LMStudioConfig {
  const baseUrl = normalizeLMStudioBaseUrl(env.LMSTUDIO_BASE_URL ?? DEFAULT_LMSTUDIO_BASE_URL);
  const model = env.LMSTUDIO_MODEL?.trim() || undefined;
  return {
    baseUrl,
    openAIBaseUrl: toOpenAIBaseUrl(baseUrl),
    model,
    contextWindow: parseContextWindow(env.LMSTUDIO_CONTEXT_WINDOW),
    apiToken: env.LMSTUDIO_API_TOKEN?.trim() || undefined
  };
}
