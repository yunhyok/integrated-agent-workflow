import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\."
    r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class DistributionContractTests(unittest.TestCase):
    def test_plugin_manifest_and_required_files(self) -> None:
        manifest_path = REPO_ROOT / ".codex-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "integrated-agent-workflow")
        self.assertRegex(manifest["version"], SEMVER_RE)
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(manifest["mcpServers"], "./.mcp.json")
        self.assertNotIn("Write", manifest["interface"]["capabilities"])
        self.assertNotIn("license", manifest)

        required = (
            ".mcp.json",
            "run-mcp.ps1",
            "install.ps1",
            "uninstall.ps1",
            "multi_agent_mcp.py",
            "requirements.txt",
            "skills/integrated-agent-flow/SKILL.md",
            "skills/integrated-agent-flow/agents/openai.yaml",
            "skills/integrated-agent-flow/references/implementation.md",
            "skills/integrated-agent-flow/references/review.md",
            "skills/integrated-agent-flow/scripts/Enable-LunaV2.ps1",
        )
        for relative_path in required:
            with self.subTest(path=relative_path):
                self.assertTrue((REPO_ROOT / relative_path).is_file())

    def test_mcp_uses_the_hardened_python_launcher(self) -> None:
        config = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(list(config["mcpServers"]), ["multi_agent"])
        server = config["mcpServers"]["multi_agent"]

        self.assertEqual(server["command"].lower(), "powershell.exe")
        self.assertIn("./run-mcp.ps1", server["args"])
        self.assertEqual(server["cwd"], ".")
        self.assertGreaterEqual(server["startup_timeout_sec"], 20)
        self.assertGreater(server["tool_timeout_sec"], server["startup_timeout_sec"])
        self.assertIn("LM_API_TOKEN", server["env_vars"])
        self.assertNotIn("node", " ".join(server["args"]).lower())

    def test_distribution_has_one_skill_and_no_legacy_typescript_runtime(self) -> None:
        skill_files = sorted(
            path.relative_to(REPO_ROOT).as_posix()
            for path in (REPO_ROOT / "skills").glob("*/SKILL.md")
        )
        self.assertEqual(skill_files, ["skills/integrated-agent-flow/SKILL.md"])
        self.assertFalse((REPO_ROOT / "mcp-server").exists())
        self.assertFalse((REPO_ROOT / "docs" / "superpowers").exists())
        self.assertEqual(list(REPO_ROOT.rglob("*.ts")), [])

    def test_no_license_disclosure_is_explicit(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("No open-source license has been selected", readme)
        self.assertIn("Public repository visibility alone", readme)


if __name__ == "__main__":
    unittest.main()
