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
        self.assertEqual(manifest["version"], "0.6.1")
        self.assertEqual(
            manifest["interface"]["displayName"],
            "Integrated Agent Workflow v0.6.1",
        )
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
            "tests/luna_v2_smoke.ps1",
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

    def test_skill_contract_and_interface_metadata(self) -> None:
        skill_dir = REPO_ROOT / "skills" / "integrated-agent-flow"
        skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        frontmatter_match = re.match(
            r"\A---\r?\n(?P<frontmatter>.*?)\r?\n---\r?\n",
            skill_text,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(frontmatter_match)
        assert frontmatter_match is not None

        frontmatter: dict[str, str] = {}
        for line in frontmatter_match.group("frontmatter").splitlines():
            key, separator, value = line.partition(":")
            self.assertEqual(separator, ":", msg=f"Invalid frontmatter line: {line}")
            frontmatter[key.strip()] = value.strip().strip('"')

        self.assertEqual(set(frontmatter), {"name", "description"})
        self.assertEqual(frontmatter["name"], "integrated-agent-flow")
        self.assertIn("Use for", frontmatter["description"])
        self.assertLessEqual(len(frontmatter["description"].split()), 100)
        self.assertLessEqual(len(skill_text.splitlines()), 500)

        self.assertIn("`claude-opus-5`", skill_text)
        self.assertIn("Never use the `opus` alias", skill_text)
        self.assertIn("Do not claim that a skill can inspect or switch", skill_text)
        self.assertNotIn("mcp__multi_agent", skill_text)
        self.assertNotIn("calling GPT-5.6 Sol Codex session", skill_text)
        self.assertNotIn("continue under GPT-5.6 Sol", skill_text)

        reference_links = set(re.findall(r"\]\((references/[^)]+)\)", skill_text))
        self.assertEqual(
            reference_links,
            {"references/implementation.md", "references/review.md"},
        )
        for relative_reference in reference_links:
            with self.subTest(reference=relative_reference):
                self.assertTrue((skill_dir / relative_reference).is_file())

        interface_text = (skill_dir / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        self.assertRegex(
            interface_text,
            r'(?m)^\s+display_name: "Integrated Agent Flow"$',
        )
        short_description = re.search(
            r'(?m)^\s+short_description: "([^"]+)"$', interface_text
        )
        self.assertIsNotNone(short_description)
        assert short_description is not None
        self.assertGreaterEqual(len(short_description.group(1)), 25)
        self.assertLessEqual(len(short_description.group(1)), 64)
        self.assertRegex(
            interface_text,
            r'(?m)^\s+default_prompt: ".*\$integrated-agent-flow.*"$',
        )

    def test_readme_documents_version_and_clean_v05_skill_migration(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.startswith("# Integrated Agent Workflow v0.6.1\n"))
        self.assertIn("`claude-opus-5`", readme)
        self.assertIn("`loaded_instances[].id`", readme)
        self.assertIn("-EnableUnconfinedCopilotReviewer", readme)
        self.assertIn("MULTI_AGENT_ENABLE_UNCONFINED_COPILOT_REVIEWER", readme)
        self.assertIn("do not overlay", readme)
        for legacy_skill in (
            "multi-agent-orchestration",
            "multi-agent-implementation",
            "multi-agent-review",
        ):
            with self.subTest(legacy_skill=legacy_skill):
                self.assertIn(legacy_skill, readme)

    def test_ci_runs_luna_behavior_smoke(self) -> None:
        ci_script = (REPO_ROOT / "tests" / "ci.ps1").read_text(encoding="utf-8")
        self.assertIn("tests\\luna_v2_smoke.ps1", ci_script)

    def test_installer_router_timeout_matches_runtime_limit(self) -> None:
        installer = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")
        self.assertRegex(
            installer,
            r"\[ValidateRange\(1, 3600\)\]\s*\[int\]\$RouterTimeoutSec",
        )
        self.assertRegex(
            installer,
            r"Parameter = 'RouterTimeoutSec';[^\r\n]+Maximum = 3600",
        )

    def test_no_license_disclosure_is_explicit(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("No open-source license has been selected", readme)
        self.assertIn("Public repository visibility alone", readme)


if __name__ == "__main__":
    unittest.main()
