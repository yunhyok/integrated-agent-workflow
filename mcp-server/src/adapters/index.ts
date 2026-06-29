import { antigravityAdapter } from "./antigravity.js";
import { claudeAdapter } from "./claude.js";
import { copilotAdapter } from "./copilot.js";

export const adapters = {
  claude: claudeAdapter,
  copilot: copilotAdapter,
  antigravity: antigravityAdapter
} as const;
