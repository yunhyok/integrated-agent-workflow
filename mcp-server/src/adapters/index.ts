import { antigravityAdapter } from "./antigravity.js";
import { claudeAdapter } from "./claude.js";
import { codexAdapter } from "./codex.js";
import { copilotAdapter } from "./copilot.js";
import { lmstudioAdapter } from "./lmstudio.js";

export const adapters = {
  codex: codexAdapter,
  lmstudio: lmstudioAdapter,
  claude: claudeAdapter,
  copilot: copilotAdapter,
  antigravity: antigravityAdapter
} as const;
