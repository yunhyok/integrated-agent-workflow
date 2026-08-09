import { getLMStudioConfig, type LMStudioConfig } from "../common/lmstudio-config.js";

type FetchLike = (input: string | URL, init?: RequestInit) => Promise<Response>;

interface NativeModel {
  type?: string;
  key?: string;
  display_name?: string;
  params_string?: string | null;
  quantization?: { name?: string | null } | null;
  loaded_instances?: Array<{ id?: string }>;
  max_context_length?: number;
  capabilities?: { trained_for_tool_use?: boolean; vision?: boolean };
  variants?: string[];
}

export interface LMStudioModelInfo {
  id: string;
  key?: string;
  displayName: string;
  loaded: boolean;
  isDefault: boolean;
  params?: string;
  quantization?: string;
  maxContextLength?: number;
  trainedForToolUse?: boolean;
  vision?: boolean;
}

export interface LMStudioModelsResult {
  provider: "lmstudio";
  status: "available" | "unavailable";
  baseUrl: string;
  openAIBaseUrl: string;
  configuredModel?: string;
  configuredModelAvailable: boolean;
  models: LMStudioModelInfo[];
  warnings: string[];
  errorMessage?: string;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function asBoolean(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

async function fetchJson(fetchImpl: FetchLike, url: string, config: LMStudioConfig, timeoutMs: number) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (config.apiToken) headers.Authorization = `Bearer ${config.apiToken}`;
    const response = await fetchImpl(url, { headers, signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}`.trim());
    try {
      return await response.json() as unknown;
    } catch {
      throw new Error("Invalid JSON response.");
    }
  } finally {
    clearTimeout(timer);
  }
}

function parseNativeModels(value: unknown): { models: NativeModel[]; valid: boolean; warnings: string[] } {
  const rawModels = asRecord(value)?.models;
  if (!Array.isArray(rawModels)) {
    return { models: [], valid: false, warnings: ["Native model list returned an unexpected schema."] };
  }

  const warnings: string[] = [];
  const models = rawModels.flatMap((value, index): NativeModel[] => {
    const record = asRecord(value);
    if (!record) {
      warnings.push(`Native model entry ${index} was not an object and was ignored.`);
      return [];
    }

    const rawLoadedInstances = record.loaded_instances;
    if (rawLoadedInstances !== undefined && !Array.isArray(rawLoadedInstances)) {
      warnings.push(`Native model entry ${index} had invalid loaded_instances metadata.`);
    }
    const loadedInstances = Array.isArray(rawLoadedInstances)
      ? rawLoadedInstances.flatMap((instance): Array<{ id: string }> => {
          const id = asString(asRecord(instance)?.id);
          return id ? [{ id }] : [];
        })
      : [];

    const rawVariants = record.variants;
    if (rawVariants !== undefined && !Array.isArray(rawVariants)) {
      warnings.push(`Native model entry ${index} had invalid variants metadata.`);
    }
    const variants = Array.isArray(rawVariants)
      ? rawVariants.filter((variant): variant is string => typeof variant === "string")
      : [];
    const quantization = asRecord(record.quantization);
    const capabilities = asRecord(record.capabilities);

    return [{
      type: asString(record.type),
      key: asString(record.key),
      display_name: asString(record.display_name),
      params_string: record.params_string === null ? null : asString(record.params_string),
      quantization: quantization ? { name: quantization.name === null ? null : asString(quantization.name) } : undefined,
      loaded_instances: loadedInstances,
      max_context_length: asNumber(record.max_context_length),
      capabilities: capabilities
        ? {
            trained_for_tool_use: asBoolean(capabilities.trained_for_tool_use),
            vision: asBoolean(capabilities.vision)
          }
        : undefined,
      variants
    }];
  });

  return { models, valid: true, warnings };
}

function parseCompatibleModelIds(value: unknown): { ids: string[]; valid: boolean } {
  const data = asRecord(value)?.data;
  if (!Array.isArray(data)) return { ids: [], valid: false };
  return { ids: data
    .map(asRecord)
    .map((item) => item?.id)
    .filter((id): id is string => typeof id === "string" && id.length > 0), valid: true };
}

function errorText(reason: unknown): string {
  return reason instanceof Error ? reason.message.slice(0, 500) : String(reason).slice(0, 500);
}

export async function listLMStudioModels(options: {
  config?: LMStudioConfig;
  fetchImpl?: FetchLike;
  timeoutMs?: number;
} = {}): Promise<LMStudioModelsResult> {
  const config = options.config ?? getLMStudioConfig();
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? 5_000;
  const [nativeResult, compatibleResult] = await Promise.allSettled([
    fetchJson(fetchImpl, `${config.baseUrl}/api/v1/models`, config, timeoutMs),
    fetchJson(fetchImpl, `${config.openAIBaseUrl}/models`, config, timeoutMs)
  ]);

  const warnings: string[] = [];
  if (nativeResult.status === "rejected") warnings.push(`Native model list failed: ${errorText(nativeResult.reason)}`);
  if (compatibleResult.status === "rejected") {
    warnings.push(`OpenAI-compatible model list failed: ${errorText(compatibleResult.reason)}`);
  }
  const nativeParsed = nativeResult.status === "fulfilled"
    ? parseNativeModels(nativeResult.value)
    : { models: [], valid: false, warnings: [] };
  const compatibleParsed = compatibleResult.status === "fulfilled"
    ? parseCompatibleModelIds(compatibleResult.value)
    : { ids: [], valid: false };
  warnings.push(...nativeParsed.warnings);
  if (compatibleResult.status === "fulfilled" && !compatibleParsed.valid) {
    warnings.push("OpenAI-compatible model list returned an unexpected schema.");
  }
  if (!nativeParsed.valid && !compatibleParsed.valid) {
    return {
      provider: "lmstudio",
      status: "unavailable",
      baseUrl: config.baseUrl,
      openAIBaseUrl: config.openAIBaseUrl,
      configuredModel: config.model,
      configuredModelAvailable: false,
      models: [],
      warnings,
      errorMessage: warnings.join("; ")
    };
  }

  const nativeModels = nativeParsed.models;
  const compatibleIds = compatibleParsed.ids;
  const metadataById = new Map<string, NativeModel>();
  const candidateIds = new Set<string>(compatibleIds);

  for (const model of nativeModels) {
    if (!model.key) continue;
    const loadedIds = (model.loaded_instances ?? [])
      .map((instance) => instance.id)
      .filter((id): id is string => Boolean(id));
    for (const id of [model.key, ...loadedIds, ...(model.variants ?? [])]) {
      metadataById.set(id, model);
    }
    if (model.type !== "llm") continue;
    candidateIds.add(model.key);
    for (const id of loadedIds) candidateIds.add(id);
  }

  const models = [...candidateIds]
    .filter((id) => metadataById.get(id)?.type !== "embedding")
    .map((id): LMStudioModelInfo => {
      const metadata = metadataById.get(id);
      const loadedIds = (metadata?.loaded_instances ?? [])
        .map((instance) => instance.id)
        .filter((value): value is string => Boolean(value));
      return {
        id,
        key: metadata?.key,
        displayName: metadata?.display_name ?? id,
        loaded: loadedIds.includes(id) || Boolean(metadata?.key === id && loadedIds.length),
        isDefault: id === config.model,
        params: metadata?.params_string ?? undefined,
        quantization: metadata?.quantization?.name ?? undefined,
        maxContextLength: metadata?.max_context_length,
        trainedForToolUse: metadata?.capabilities?.trained_for_tool_use,
        vision: metadata?.capabilities?.vision
      };
    })
    .sort((a, b) => Number(b.isDefault) - Number(a.isDefault) || Number(b.loaded) - Number(a.loaded) || a.id.localeCompare(b.id));

  return {
    provider: "lmstudio",
    status: "available",
    baseUrl: config.baseUrl,
    openAIBaseUrl: config.openAIBaseUrl,
    configuredModel: config.model,
    configuredModelAvailable: Boolean(config.model && models.some((model) => model.id === config.model)),
    models,
    warnings
  };
}
