import ctypes
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

import multi_agent_mcp as router


class ModelMetadataTests(unittest.TestCase):
    def test_agent_result_renders_model_beside_agent(self):
        result = router.AgentResult("Claude", "claude-sonnet-4-6", "answer")
        self.assertEqual(
            result.render(),
            "## Claude (model: claude-sonnet-4-6)\n\nanswer",
        )

    @unittest.skipUnless(os.name == "nt", "Windows process-tree regression")
    def test_timeout_terminates_descendant_process_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_path = Path(directory) / "child.pid"
            helper = (
                "import subprocess,sys,time; from pathlib import Path; "
                "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
                f"Path({str(pid_path)!r}).write_text(str(child.pid),encoding='ascii'); "
                "time.sleep(30)"
            )
            with self.assertRaises(router.subprocess.TimeoutExpired):
                router._run_agent_process([sys.executable, "-c", helper], directory, 1)
            child_pid = int(pid_path.read_text(encoding="ascii"))
            deadline = time.monotonic() + 3
            still_active = True
            while still_active and time.monotonic() < deadline:
                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, child_pid)
                if not handle:
                    still_active = False
                    break
                exit_code = ctypes.c_ulong()
                ctypes.windll.kernel32.GetExitCodeProcess(
                    handle, ctypes.byref(exit_code)
                )
                ctypes.windll.kernel32.CloseHandle(handle)
                still_active = exit_code.value == 259
                if still_active:
                    time.sleep(0.1)
            self.assertFalse(
                still_active, "Timed-out reviewer descendant remained alive"
            )

    def test_reviewer_output_capture_is_bounded(self):
        helper = "import sys;sys.stdout.write('x'*256)"
        with (
            patch.object(router, "MAX_PROCESS_OUTPUT_BYTES", 128),
            self.assertRaisesRegex(router.subprocess.SubprocessError, "8 MiB"),
        ):
            router._run_agent_process(
                [sys.executable, "-c", helper], str(Path.cwd()), 10
            )

    def test_parse_codex_jsonl(self):
        output = (
            '{"type":"item.completed","item":{"type":"agent_message",'
            '"text":"CODEX_OK"}}\n'
        )
        self.assertEqual(router._parse_codex_output(output), "CODEX_OK")

    def test_parse_claude_stream_json(self):
        output = (
            '{"type":"system","model":"claude-sonnet-4-6"}\n'
            '{"type":"assistant","message":{"model":"claude-sonnet-4-6",'
            '"content":[{"type":"text","text":"CLAUDE_OK"}]}}\n'
            '{"type":"result","result":"CLAUDE_OK"}\n'
        )
        self.assertEqual(
            router._parse_claude_output(output),
            ("CLAUDE_OK", "claude-sonnet-4-6"),
        )

    def test_parse_claude_model_usage_preserves_all_observed_models(self):
        output = (
            '{"type":"system","model":"claude-opus-5"}\n'
            '{"type":"result","result":"OK","modelUsage":'
            '{"claude-haiku-4-5":{},"claude-opus-5":{}}}\n'
        )
        answer, model, observed = router._parse_claude_output_details(output)
        self.assertEqual(answer, "OK")
        self.assertEqual(model, "claude-opus-5")
        self.assertEqual(observed, ("claude-haiku-4-5", "claude-opus-5"))

    def test_parse_claude_ignores_non_string_text(self):
        output = (
            '{"type":"assistant","message":{"model":"claude-sonnet-4-6",'
            '"content":[{"type":"text","text":42}]}}\n'
            '{"type":"result","result":{"text":"not-a-string"}}\n'
        )
        self.assertEqual(
            router._parse_claude_output_details(output),
            (None, "claude-sonnet-4-6", ("claude-sonnet-4-6",)),
        )

    def test_primary_claude_model_takes_precedence_over_usage_models(self):
        result = router.AgentResult(
            "Claude",
            "claude-haiku-4-5",
            "UNTRUSTED_PROVIDER_TEXT",
            requested_model="claude-opus-5",
            observed_models=("claude-opus-5", "claude-haiku-4-5"),
        )
        payload = router._structured_agent_payload("claude", "claude-opus-5", result, 1)
        self.assertEqual(payload["modelMatch"], "mismatch")
        self.assertEqual(payload["status"], "invalid_output")
        self.assertNotIn("UNTRUSTED_PROVIDER_TEXT", payload["resultText"])

    def test_parse_copilot_jsonl(self):
        output = (
            '{"type":"session.tools_updated","data":{"model":"gpt-5.4"}}\n'
            '{"type":"assistant.message","data":{"model":"gpt-5.4",'
            '"content":"COPILOT_OK"}}\n'
        )
        self.assertEqual(
            router._parse_copilot_output(output),
            ("COPILOT_OK", "gpt-5.4"),
        )

    def test_parse_antigravity_transcript(self):
        with tempfile.TemporaryDirectory() as directory:
            transcript = Path(directory) / "transcript.jsonl"
            transcript.write_text(
                '{"source":"USER_EXPLICIT","content":"The user changed setting '
                '`Model Selection` from None to Gemini 3.1 Pro (High). No need to comment."}\n'
                '{"source":"TOOL","content":"changed setting `Model Selection` from .*? '
                'to (.+?). No need"}\n'
                '{"source":"MODEL","content":"ANTIGRAVITY_OK"}\n',
                encoding="utf-8",
            )
            self.assertEqual(
                router._extract_antigravity_details(transcript),
                ("ANTIGRAVITY_OK", "Gemini 3.1 Pro (High)"),
            )

    def test_antigravity_transcript_is_correlated_by_run_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            appdata = Path(directory)
            correct = (
                appdata
                / "brain"
                / "correct"
                / ".system_generated"
                / "logs"
                / "transcript.jsonl"
            )
            wrong = (
                appdata
                / "brain"
                / "wrong"
                / ".system_generated"
                / "logs"
                / "transcript.jsonl"
            )
            correct.parent.mkdir(parents=True)
            wrong.parent.mkdir(parents=True)
            correct.write_text(
                '{"content":"router-run-id:expected"}\n', encoding="utf-8"
            )
            wrong.write_text('{"content":"router-run-id:other"}\n', encoding="utf-8")
            with patch.object(router, "AGY_APPDATA", appdata):
                self.assertEqual(
                    router._latest_antigravity_transcript(0, "router-run-id:expected"),
                    correct,
                )

    def test_failure_prefers_cli_reported_actual_model(self):
        completed = CompletedProcess(["agent"], 1, "", "failed")
        result = router._agent_failure(
            "Claude",
            "sonnet",
            completed,
            1000,
            "claude-sonnet-4-6",
        )
        self.assertEqual(result.model, "claude-sonnet-4-6")

    def test_safe_call_discards_legacy_model_substitution(self):
        result = router._safe_agent_call(
            "Claude",
            "claude-opus-5",
            lambda: router.AgentResult(
                "Claude",
                "claude-haiku-4-5",
                "UNTRUSTED_PROVIDER_TEXT",
                requested_model="claude-opus-5",
                observed_models=("claude-haiku-4-5",),
                exit_code=0,
            ),
        )
        self.assertEqual(result.status, "invalid_output")
        self.assertNotIn("UNTRUSTED_PROVIDER_TEXT", result.render())
        self.assertIn("Response discarded", result.render())

    def test_legacy_render_marks_unobserved_requested_model_unverified(self):
        result = router.AgentResult(
            "Codex",
            "gpt-requested",
            "answer",
            requested_model="gpt-requested",
        )
        self.assertIn(
            "model: gpt-requested requested; actual unverified", result.render()
        )

    def test_claude_model_list_is_not_invented(self):
        self.assertEqual(router._available_models("claude"), [])

    def test_antigravity_model_list_returns_override_safe_ids(self):
        completed = CompletedProcess(
            ["agy", "models"],
            0,
            "gemini-3.1-pro-high\tGemini 3.1 Pro (High)\n"
            "gemini-3-flash\tGemini 3 Flash\n",
            "",
        )
        with (
            patch.object(router, "_resolve_command", return_value="agy"),
            patch.object(router, "_run_agent_process", return_value=completed),
        ):
            models = router._available_models("antigravity")
        self.assertEqual(models, ["gemini-3.1-pro-high", "gemini-3-flash"])
        for model in models:
            router._validate_cli_model(model)

    def test_antigravity_display_label_canonicalizes_to_catalog_id(self):
        with patch.object(
            router,
            "_antigravity_model_catalog",
            return_value={"gemini-3.1-pro-high": "Gemini 3.1 Pro (High)"},
        ):
            observed = router._canonicalize_antigravity_model("Gemini 3.1 Pro (High)")
        self.assertEqual(observed, "gemini-3.1-pro-high")

    def test_readonly_rules_are_kept_for_exact_reply_requests(self):
        prompt = router._readonly_prompt("Reply with only: ROUTER_OK", str(Path.cwd()))
        self.assertIn("Work read-only", prompt)
        self.assertIn("Reply with only: ROUTER_OK", prompt)

    def test_augmented_env_strips_credentials_and_permissive_flags(self):
        with patch.dict(
            router.os.environ,
            {
                "LM_API_TOKEN": "secret",
                "MULTI_AGENT_LM_STUDIO_API_KEY": "secret",
                "COPILOT_ALLOW_ALL": "1",
                "GITHUB_COPILOT_PROMPT_MODE_WORKSPACE_MCP": "1",
                "AGY_DANGEROUSLY_SKIP_PERMISSIONS": "1",
                "AWS_SECRET_ACCESS_KEY": "aws-secret",
                "ANTHROPIC_API_KEY": "claude-secret",
                "COPILOT_GITHUB_TOKEN": "copilot-secret",
            },
        ):
            env = router._augmented_env(("ANTHROPIC_API_KEY",))
            copilot_env = router._augmented_env(("COPILOT_GITHUB_TOKEN",))
        self.assertNotIn("LM_API_TOKEN", env)
        self.assertNotIn("MULTI_AGENT_LM_STUDIO_API_KEY", env)
        self.assertNotIn("COPILOT_ALLOW_ALL", env)
        self.assertNotIn("GITHUB_COPILOT_PROMPT_MODE_WORKSPACE_MCP", env)
        self.assertNotIn("AGY_DANGEROUSLY_SKIP_PERMISSIONS", env)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env)
        self.assertEqual(env["ANTHROPIC_API_KEY"], "claude-secret")
        self.assertEqual(copilot_env["COPILOT_GITHUB_TOKEN"], "copilot-secret")

    def test_process_output_redacts_environment_and_inline_secrets(self):
        completed = CompletedProcess(
            ["agent"],
            1,
            "token=inline-secret Bearer bearer-secret configured-secret "
            '"apiKey":"json-secret" https://user:url-secret@example.test',
            "password: password-secret",
        )
        with patch.dict(
            router.os.environ,
            {"EXAMPLE_ACCESS_TOKEN": "configured-secret"},
            clear=False,
        ):
            output = router._process_output(completed, 2000)
        for secret in (
            "configured-secret",
            "inline-secret",
            "bearer-secret",
            "password-secret",
            "json-secret",
            "url-secret",
        ):
            self.assertNotIn(secret, output)
        self.assertIn("[redacted]", output)

    def test_codex_command_ignores_user_customization_and_isolates_cwd(self):
        completed = CompletedProcess(
            ["codex"],
            0,
            '{"type":"item.completed","item":{"type":"agent_message","text":"OK"}}\n',
            "",
        )
        with (
            patch.object(router, "CODEX_REVIEWER_ENABLED", True),
            patch.object(router, "_resolve_codex_command", return_value="codex"),
            patch.object(router, "_codex_default_model", return_value="default"),
            patch.object(router, "_run_agent_process", return_value=completed) as run,
        ):
            result = router._ask_codex("review", str(Path.cwd()), 30, 1000)
        command = run.call_args.args[0]
        self.assertEqual(result.content, "OK")
        self.assertNotEqual(run.call_args.args[1], str(Path.cwd()))
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertEqual(
            run.call_args.kwargs["allowed_auth_env_names"], ("OPENAI_API_KEY",)
        )

    def test_claude_command_uses_safe_mode_and_isolates_cwd(self):
        completed = CompletedProcess(
            ["claude"],
            0,
            '{"type":"assistant","message":{"model":"test","content":[{"type":"text","text":"OK"}]}}\n',
            "",
        )
        with (
            patch.object(router, "_resolve_command", return_value="claude"),
            patch.object(router, "_run_agent_process", return_value=completed) as run,
        ):
            result = router._ask_claude("review", str(Path.cwd()), 30, 1000)
        command = run.call_args.args[0]
        self.assertEqual(result.content, "OK")
        self.assertNotEqual(run.call_args.args[1], str(Path.cwd()))
        self.assertIn("--safe-mode", command)

    def test_copilot_command_enforces_plan_mode_without_tools(self):
        completed = CompletedProcess(
            ["copilot"],
            0,
            '{"type":"assistant.message","data":{"model":"test","content":"OK"}}\n',
            "",
        )
        with (
            patch.object(router, "_resolve_command", return_value="copilot"),
            patch.object(router, "_run_agent_process", return_value=completed) as run,
        ):
            result = router._ask_copilot("review", str(Path.cwd()), 30, 1000)
        command = run.call_args.args[0]
        self.assertEqual(result.content, "OK")
        self.assertNotEqual(run.call_args.args[1], str(Path.cwd()))
        self.assertIn("--mode", command)
        self.assertIn("plan", command)
        self.assertIn("--available-tools=view", command)
        self.assertIn("--disable-builtin-mcps", command)
        self.assertNotIn("--attachment", command)
        self.assertNotIn("--allow-all", command)

    def test_antigravity_command_enforces_plan_and_sandbox(self):
        completed = CompletedProcess(["agy"], 0, "OK", "")
        with (
            patch.object(router, "ANTIGRAVITY_REVIEWER_ENABLED", True),
            patch.object(router, "_resolve_command", return_value="agy"),
            patch.object(router, "_run_agent_process", return_value=completed) as run,
            patch.object(router, "_latest_antigravity_transcript", return_value=None),
        ):
            result = router._ask_antigravity("review", str(Path.cwd()), 30, 1000)
        command = run.call_args.args[0]
        self.assertEqual(result.content, "OK")
        self.assertIn("--mode", command)
        self.assertIn("plan", command)
        self.assertIn("--sandbox", command)
        self.assertIn("--disable-slash-commands", command)
        self.assertNotEqual(run.call_args.args[1], str(Path.cwd()))

    def test_antigravity_rejects_oversized_direct_prompt(self):
        with (
            patch.object(router, "ANTIGRAVITY_REVIEWER_ENABLED", True),
            patch.object(router, "_resolve_command", return_value="agy"),
            patch.object(router, "ANTIGRAVITY_MAX_PROMPT_CHARS", 10),
            patch.object(router, "_run_agent_process") as run,
        ):
            result = router._ask_antigravity("review", str(Path.cwd()), 30, 1000)
        self.assertIn("too large", result.content)
        run.assert_not_called()

    def test_codex_reviewer_is_disabled_before_resolving_or_running(self):
        with (
            patch.object(router, "CODEX_REVIEWER_ENABLED", False),
            patch.object(router, "_resolve_codex_command") as resolve,
            patch.object(router, "_run_agent_process") as run,
        ):
            result = router._ask_codex("review", str(Path.cwd()), 30, 1000)
        self.assertIn("disabled by policy", result.content)
        resolve.assert_not_called()
        run.assert_not_called()

    def test_cli_models_reject_cmd_metacharacters_before_process_start(self):
        for callback in (
            router._ask_codex,
            router._ask_claude,
            router._ask_copilot,
            router._ask_antigravity,
        ):
            with (
                self.subTest(callback=callback.__name__),
                patch.object(router, "CODEX_REVIEWER_ENABLED", True),
                patch.object(router, "ANTIGRAVITY_REVIEWER_ENABLED", True),
                patch.object(router, "_resolve_command") as resolve,
                patch.object(router, "_run_agent_process") as run,
                self.assertRaises(ValueError),
            ):
                callback(
                    "review", str(Path.cwd()), 30, 1000, model="safe&echo.INJECTED"
                )
            resolve.assert_not_called()
            run.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows batch-wrapper regression")
    def test_real_batch_wrapper_canary_is_not_started_for_injected_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / "reviewer.cmd"
            marker = root / "started.txt"
            wrapper.write_text(
                '@echo off\r\n>"%~dp0started.txt" echo STARTED\r\n',
                encoding="utf-8",
            )
            for callback, env_name in (
                (router._ask_codex, "MULTI_AGENT_CODEX_CMD"),
                (router._ask_claude, "MULTI_AGENT_CLAUDE_CMD"),
                (router._ask_copilot, "MULTI_AGENT_COPILOT_CMD"),
            ):
                with (
                    self.subTest(callback=callback.__name__),
                    patch.object(router, "CODEX_REVIEWER_ENABLED", True),
                    patch.dict(router.os.environ, {env_name: str(wrapper)}),
                    self.assertRaises(ValueError),
                ):
                    callback(
                        "review",
                        str(Path.cwd()),
                        30,
                        1000,
                        model="safe&echo.INJECTED",
                    )
                self.assertFalse(marker.exists())

    def test_antigravity_rejects_batch_wrapper_for_prompt_transport(self):
        with (
            patch.object(router, "ANTIGRAVITY_REVIEWER_ENABLED", True),
            patch.object(
                router, "_resolve_command", return_value=r"C:\\agent\\agy.cmd"
            ),
            patch.object(router, "_run_agent_process") as run,
            self.assertRaisesRegex(ValueError, "native executable"),
        ):
            router._ask_antigravity("review", str(Path.cwd()), 30, 1000)
        run.assert_not_called()

    def test_antigravity_reviewer_is_disabled_before_resolving_or_running(self):
        with (
            patch.object(router, "ANTIGRAVITY_REVIEWER_ENABLED", False),
            patch.object(router, "_resolve_command") as resolve,
            patch.object(router, "_run_agent_process") as run,
        ):
            result = router._ask_antigravity("review", str(Path.cwd()), 30, 1000)
        self.assertIn("disabled by policy", result.content)
        resolve.assert_not_called()
        run.assert_not_called()


class ContextBoundaryTests(unittest.TestCase):
    def test_context_file_count_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "at most 32 files"):
            router._context_from_files(
                str(Path.cwd()), ["same.txt"] * (router.MAX_CONTEXT_FILES + 1), 1000
            )

    def test_total_context_size_boundary_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "a.txt").write_text("abc", encoding="utf-8")
            (root / "b.txt").write_text("de", encoding="utf-8")
            (root / "c.txt").write_text("f", encoding="utf-8")
            with (
                patch.object(router, "ALLOWED_CONTEXT_ROOTS", (root,)),
                patch.object(router, "MAX_TOTAL_CONTEXT_CHARS", 5),
            ):
                router._context_from_files(str(root), ["a.txt", "b.txt"], 1000)
                with self.assertRaisesRegex(ValueError, "Combined context"):
                    router._context_from_files(
                        str(root), ["a.txt", "b.txt", "c.txt"], 1000
                    )

    def test_allowed_root_accepts_relative_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "src"
            source.mkdir()
            (source / "main.py").write_text("print('ok')", encoding="utf-8")
            with patch.object(router, "ALLOWED_CONTEXT_ROOTS", (root,)):
                working_dir = router._normalize_working_dir(str(source))
                context = router._context_from_files(working_dir, ["main.py"], 1000)
            self.assertIn("print('ok')", context)
            self.assertNotIn(str(root), context)

    def test_explicit_working_dir_outside_allowed_roots_is_rejected(self):
        with (
            tempfile.TemporaryDirectory() as allowed,
            tempfile.TemporaryDirectory() as outside,
            patch.object(router, "ALLOWED_CONTEXT_ROOTS", (Path(allowed).resolve(),)),
            self.assertRaises(PermissionError),
        ):
            router._normalize_working_dir(outside)

    def test_context_is_disabled_without_configured_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "file.txt").write_text("private", encoding="utf-8")
            with (
                patch.object(router, "ALLOWED_CONTEXT_ROOTS", ()),
                self.assertRaises(PermissionError),
            ):
                router._context_from_files(str(root), ["file.txt"], 1000)

    def test_absolute_and_escaping_context_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            project = root / "project"
            project.mkdir()
            outside = root / "outside.txt"
            outside.write_text("private", encoding="utf-8")
            with patch.object(router, "ALLOWED_CONTEXT_ROOTS", (root,)):
                with self.assertRaisesRegex(ValueError, "relative"):
                    router._context_from_files(str(project), [str(outside)], 1000)
                with self.assertRaises(PermissionError):
                    router._context_from_files(str(project), [r"..\outside.txt"], 1000)

    def test_reparse_point_is_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source.txt"
            source.write_text("private", encoding="utf-8")
            with (
                patch.object(router, "ALLOWED_CONTEXT_ROOTS", (root,)),
                patch.object(
                    router, "_is_reparse_point", side_effect=lambda path: path == source
                ),
                self.assertRaisesRegex(PermissionError, "reparse point"),
            ):
                router._context_from_files(str(root), ["source.txt"], 1000)


class LMStudioTests(unittest.TestCase):
    def test_base_url_normalization_adds_v1_once(self):
        self.assertEqual(
            router._normalize_lm_studio_base_url("http://127.0.0.1:1234"),
            "http://127.0.0.1:1234/v1",
        )

    def test_base_url_normalization_rejects_unexpected_components(self):
        invalid_values = [
            "127.0.0.1:1234",
            "http://127.0.0.1:1234/custom",
            "http://127.0.0.1:1234?token=secret",
            "http://user:password@127.0.0.1:1234",
        ]
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                router._normalize_lm_studio_base_url(value)

    def test_transport_policy_allows_unauthenticated_loopback(self):
        router._validate_lm_studio_transport("http://127.0.0.1:1234/v1", "")
        router._validate_lm_studio_transport("http://[::1]:1234/v1", "")

    def test_transport_policy_rejects_wildcard_client_addresses(self):
        for value in ("http://0.0.0.0:1234/v1", "http://[::]:1234/v1"):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "wildcard"),
            ):
                router._validate_lm_studio_transport(value, "")

    def test_transport_policy_requires_https_and_auth_for_remote(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            router._validate_lm_studio_transport("http://192.0.2.10:1234/v1", "token")
        with self.assertRaisesRegex(ValueError, "API token"):
            router._validate_lm_studio_transport("https://lmstudio.example/v1", "")
        router._validate_lm_studio_transport("https://lmstudio.example/v1", "token")
        router._validate_lm_studio_transport(
            "http://192.0.2.10:1234/v1",
            "token",
            allow_insecure_remote=True,
        )

    def test_unconfigured_default_model_does_not_call_server(self):
        with (
            patch.object(router, "LM_STUDIO_DEFAULT_MODEL", ""),
            patch.object(router, "_lm_studio_model_ids") as models,
            patch.object(router, "_lm_studio_json_request") as request,
        ):
            result = router._ask_lm_studio("review", str(Path.cwd()), 30, 1000)
        self.assertEqual(result.model, "unconfigured")
        models.assert_not_called()
        request.assert_not_called()

    def test_http_200_error_object_is_rejected(self):
        response = MagicMock()
        response.read.return_value = b'{"error":"bad request"}'
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        with (
            patch.object(router.urllib.request, "build_opener", return_value=opener),
            self.assertRaisesRegex(router.LMStudioError, "bad request"),
        ):
            router._lm_studio_json_request("GET", "models", timeout_sec=1)
        self.assertEqual(
            router._normalize_lm_studio_base_url("http://127.0.0.1:1234/v1/"),
            "http://127.0.0.1:1234/v1",
        )

    def test_lm_studio_response_size_is_bounded(self):
        response = MagicMock()
        response.read.return_value = b"x" * (router.LM_STUDIO_MAX_RESPONSE_BYTES + 1)
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        with (
            patch.object(router.urllib.request, "build_opener", return_value=opener),
            self.assertRaisesRegex(router.LMStudioError, "8 MiB safety limit"),
        ):
            router._lm_studio_json_request("GET", "models", timeout_sec=1)
        response.read.assert_called_once_with(router.LM_STUDIO_MAX_RESPONSE_BYTES + 1)

    def test_error_detail_redacts_configured_token(self):
        with patch.object(router, "LM_STUDIO_API_KEY", "secret-token"):
            detail = router._lm_studio_error_detail(
                '{"error":"reflected secret-token"}'
            )
        self.assertEqual(detail, "reflected [redacted]")

    def test_error_detail_redacts_short_configured_token(self):
        with patch.object(router, "LM_STUDIO_API_KEY", "abc"):
            detail = router._lm_studio_error_detail('{"error":"reflected abc"}')
        self.assertEqual(detail, "reflected [redacted]")

    def test_lm_studio_redirects_are_rejected(self):
        redirect = router.urllib.error.HTTPError(
            "http://127.0.0.1:1234/v1/models",
            302,
            "Found",
            {"Location": "http://127.0.0.1:4321/capture"},
            None,
        )
        opener = MagicMock()
        opener.open.side_effect = redirect
        with (
            patch.object(router.urllib.request, "build_opener", return_value=opener),
            self.assertRaisesRegex(router.LMStudioError, "redirects are not allowed"),
        ):
            router._lm_studio_json_request("GET", "models", timeout_sec=1)

    def test_model_list_uses_native_api_and_filters_embeddings(self):
        response = {
            "models": [
                {"key": "google/gemma-4-12b-qat", "type": "llm"},
                {"key": "text-embedding-nomic-embed-text-v1.5", "type": "embedding"},
            ],
        }
        with patch.object(router, "_lm_studio_json_request", return_value=response):
            self.assertEqual(
                router._lm_studio_model_ids(),
                ["google/gemma-4-12b-qat"],
            )

    def test_rich_model_discovery_merges_endpoints_and_preserves_metadata(self):
        native = {
            "models": [
                {
                    "key": "org/model",
                    "type": "llm",
                    "display_name": "Model",
                    "params_string": "12B",
                    "quantization": {"name": "Q4_K_M"},
                    "loaded_instances": [{"id": "org/model@q4"}],
                    "max_context_length": 32768,
                    "capabilities": {
                        "trained_for_tool_use": True,
                        "vision": False,
                    },
                    "variants": ["org/model:q8"],
                },
                {
                    "key": "embed/model",
                    "type": "embedding",
                    "loaded_instances": [{"id": "embed/model@loaded"}],
                },
            ]
        }
        compatible = {
            "data": [
                {"id": "org/model@q4"},
                {"id": "compatible-only"},
                {"id": "embed/model"},
            ]
        }

        def request(method, path, payload=None, timeout_sec=15):
            del method, payload, timeout_sec
            return native if path == "api/v1/models" else compatible

        with (
            patch.object(router, "_lm_studio_json_request", side_effect=request),
            patch.object(router, "LM_STUDIO_DEFAULT_MODEL", "org/model@q4"),
        ):
            result = router._lm_studio_models_result()
        by_id = {item["id"]: item for item in result["models"]}
        self.assertEqual(result["status"], "available")
        self.assertTrue(result["configuredModelAvailable"])
        self.assertIn("org/model", by_id)
        self.assertIn("org/model@q4", by_id)
        self.assertIn("compatible-only", by_id)
        self.assertNotIn("embed/model", by_id)
        self.assertNotIn("embed/model@loaded", by_id)
        self.assertTrue(by_id["org/model@q4"]["loaded"])
        self.assertEqual(by_id["org/model@q4"]["quantization"], "Q4_K_M")
        self.assertEqual(by_id["org/model@q4"]["maxContextLength"], 32768)
        self.assertTrue(by_id["org/model@q4"]["trainedForToolUse"])
        self.assertEqual(by_id["org/model@q4"]["loadedInstanceIds"], ["org/model@q4"])
        self.assertEqual(by_id["org/model@q4"]["variants"], ["org/model:q8"])

    def test_list_agent_models_reports_lm_studio_unavailable(self):
        with patch.object(
            router,
            "_available_models",
            side_effect=router.LMStudioError("server stopped"),
        ):
            result = router.list_agent_models("lmstudio")
        self.assertIn("## LM Studio", result)
        self.assertIn("unavailable: server stopped", result)

    def test_list_agent_models_accepts_lm_studio_alias(self):
        with patch.object(
            router,
            "_available_models",
            return_value=["google/gemma-4-12b-qat"],
        ):
            result = router.list_agent_models("lm_studio")
        self.assertIn("## LM Studio", result)
        self.assertIn("google/gemma-4-12b-qat", result)

    def test_chat_response_extracts_actual_model_and_finish_reason(self):
        response = {
            "model": "google/gemma-4-12b-qat",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "LMSTUDIO_OK"},
                    "finish_reason": "stop",
                }
            ],
        }
        self.assertEqual(
            router._extract_lm_studio_chat_response(response),
            ("LMSTUDIO_OK", "google/gemma-4-12b-qat", "stop"),
        )

    def test_ask_lm_studio_sends_supported_parameters(self):
        response = {
            "model": "google/gemma-4-12b-qat",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "LMSTUDIO_OK"},
                    "finish_reason": "stop",
                }
            ],
        }
        with (
            patch.object(
                router,
                "_lm_studio_model_ids",
                return_value=["google/gemma-4-12b-qat"],
            ),
            patch.object(
                router, "_lm_studio_json_request", return_value=response
            ) as request,
        ):
            result = router._ask_lm_studio(
                "Reply with only: LMSTUDIO_OK",
                str(Path.cwd()),
                60,
                1000,
                model="google/gemma-4-12b-qat",
            )
        self.assertEqual(result.content, "LMSTUDIO_OK")
        payload = request.call_args.args[2]
        self.assertEqual(payload["model"], "google/gemma-4-12b-qat")
        self.assertEqual(payload["reasoning_effort"], "none")
        self.assertFalse(payload["stream"])

    def test_ask_lm_studio_can_omit_reasoning_effort(self):
        response = {
            "model": "google/gemma-4-12b-qat",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "OK"},
                    "finish_reason": "stop",
                }
            ],
        }
        with (
            patch.object(
                router,
                "_lm_studio_model_ids",
                return_value=["google/gemma-4-12b-qat"],
            ),
            patch.object(
                router, "_lm_studio_json_request", return_value=response
            ) as request,
        ):
            router._ask_lm_studio(
                "review",
                str(Path.cwd()),
                60,
                1000,
                model="google/gemma-4-12b-qat",
                max_tokens=64,
                reasoning_effort=None,
            )
        payload = request.call_args.args[2]
        self.assertEqual(payload["max_tokens"], 64)
        self.assertNotIn("reasoning_effort", payload)

    def test_ask_lm_studio_rejects_unadvertised_model_before_chat(self):
        with (
            patch.object(
                router,
                "_lm_studio_model_ids",
                return_value=["google/gemma-4-12b-qat"],
            ),
            patch.object(router, "_lm_studio_json_request") as request,
        ):
            result = router._ask_lm_studio(
                "review",
                str(Path.cwd()),
                60,
                1000,
                model="invalid/probe-model",
            )
        request.assert_not_called()
        self.assertIn("not advertised", result.content)

    def test_ask_lm_studio_discards_silent_model_substitution(self):
        response = {
            "model": "other/model",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "wrong model answer"},
                    "finish_reason": "stop",
                }
            ],
        }
        with (
            patch.object(
                router,
                "_lm_studio_model_ids",
                return_value=["google/gemma-4-12b-qat"],
            ),
            patch.object(router, "_lm_studio_json_request", return_value=response),
        ):
            result = router._ask_lm_studio(
                "review",
                str(Path.cwd()),
                60,
                1000,
                model="google/gemma-4-12b-qat",
            )
        self.assertEqual(result.model, "other/model")
        self.assertIn("Response discarded", result.content)

    def test_ask_lm_studio_reports_reasoning_budget_exhaustion(self):
        response = {
            "model": "google/gemma-4-12b-qat",
            "choices": [
                {
                    "message": {"role": "assistant", "content": ""},
                    "finish_reason": "length",
                }
            ],
            "usage": {"completion_tokens_details": {"reasoning_tokens": 64}},
        }
        with (
            patch.object(
                router,
                "_lm_studio_model_ids",
                return_value=["google/gemma-4-12b-qat"],
            ),
            patch.object(router, "_lm_studio_json_request", return_value=response),
        ):
            result = router._ask_lm_studio(
                "review",
                str(Path.cwd()),
                60,
                1000,
                model="google/gemma-4-12b-qat",
            )
        self.assertIn("finish_reason: length", result.content)
        self.assertIn("Reasoning tokens consumed: 64", result.content)

    def test_collect_reviews_routes_lm_studio_options(self):
        expected = router.AgentResult(
            "LM Studio",
            "google/gemma-4-12b-qat",
            "LOCAL_REVIEW",
        )
        working_dir = str(Path.cwd())
        with (
            patch.object(
                router, "ALLOWED_CONTEXT_ROOTS", (Path(working_dir).resolve(),)
            ),
            patch.object(router, "_ask_lm_studio", return_value=expected) as ask,
        ):
            result = router.collect_reviews(
                "review",
                working_dir=working_dir,
                context_files=["README.md"],
                include_codex=False,
                include_claude=False,
                include_copilot=False,
                include_antigravity=False,
                include_lm_studio=True,
                lm_studio_model="google/gemma-4-12b-qat",
                lm_studio_max_tokens=64,
                lm_studio_reasoning_effort=None,
                timeout_sec=30,
            )
        self.assertIn("LOCAL_REVIEW", result)
        ask.assert_called_once()
        self.assertIn("Authorized context snapshot", ask.call_args.args[0])
        self.assertEqual(
            ask.call_args.args[1:4], (working_dir, 30, router.DEFAULT_MAX_CHARS)
        )
        self.assertIsNone(ask.call_args.args[4])
        self.assertEqual(
            ask.call_args.args[5:],
            ("google/gemma-4-12b-qat", 64, None),
        )

    def test_collect_reviews_cannot_enable_policy_disabled_codex(self):
        with (
            patch.object(router, "CODEX_REVIEWER_ENABLED", False),
            patch.object(router, "_resolve_codex_command") as resolve,
            patch.object(router, "_run_agent_process") as run,
        ):
            result = router.collect_reviews(
                "review",
                include_codex=True,
                include_claude=False,
                include_copilot=False,
                include_antigravity=False,
                include_lm_studio=False,
            )
        self.assertIn("disabled by policy", result)
        resolve.assert_not_called()
        run.assert_not_called()

    def test_collect_reviews_keeps_lm_studio_opt_in(self):
        with patch.object(router, "_ask_lm_studio") as ask:
            result = router.collect_reviews(
                "review",
                include_codex=False,
                include_claude=False,
                include_copilot=False,
                include_antigravity=False,
            )
        self.assertEqual(result, "No agents were selected.")
        ask.assert_not_called()

    def test_collect_reviews_preflights_all_models_before_starting(self):
        with (
            patch.object(router, "_ask_claude") as claude,
            patch.object(router, "_ask_copilot") as copilot,
            self.assertRaises(ValueError),
        ):
            router.collect_reviews(
                "review",
                include_claude=True,
                include_copilot=True,
                copilot_model="safe&echo.INJECTED",
            )
        claude.assert_not_called()
        copilot.assert_not_called()


class StructuredApiTests(unittest.TestCase):
    def _workspace(self):
        path = Path.cwd().resolve()
        return str(path), (path,)

    def test_mcp_schema_exposes_structured_tools_and_closed_policy_enums(self):
        tools = {tool.name: tool for tool in router.mcp._tool_manager.list_tools()}
        self.assertTrue(
            {"doctor", "list_lmstudio_models", "run_agent", "run_panel"}.issubset(tools)
        )
        agent_schema = tools["run_agent"].parameters["properties"]
        self.assertEqual(
            agent_schema["agent_id"]["enum"],
            ["codex", "lmstudio", "claude", "copilot", "antigravity"],
        )
        self.assertEqual(
            agent_schema["purpose"]["enum"],
            ["general", "implementation", "review"],
        )
        self.assertEqual(
            agent_schema["write_policy"]["enum"],
            ["read_only", "patch_proposal"],
        )

    def test_run_agent_returns_stable_model_evidence_contract(self):
        working_dir, roots = self._workspace()
        expected = router.AgentResult(
            "Claude",
            "claude-opus-5",
            "REVIEW_OK",
            requested_model="claude-opus-5",
            observed_models=("claude-haiku-4-5", "claude-opus-5"),
            exit_code=0,
        )
        with (
            patch.object(router, "ALLOWED_CONTEXT_ROOTS", roots),
            patch.object(router, "_ask_claude", return_value=expected) as ask,
        ):
            payload = json.loads(
                router.run_agent(
                    "claude",
                    "Review the parser.",
                    working_dir=working_dir,
                    purpose="review",
                    acceptance_criteria=["Identify concrete risks."],
                    models={"claude": "claude-opus-5"},
                    write_policy="patch_proposal",
                )
            )
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(
            set(payload),
            {
                "schemaVersion",
                "agentId",
                "displayName",
                "requestedModel",
                "observedModels",
                "modelMatch",
                "status",
                "createdAt",
                "durationMs",
                "exitCode",
                "resultText",
                "errorMessage",
            },
        )
        self.assertEqual(payload["agentId"], "claude")
        self.assertEqual(payload["requestedModel"], "claude-opus-5")
        self.assertEqual(
            payload["observedModels"],
            ["claude-haiku-4-5", "claude-opus-5"],
        )
        self.assertEqual(payload["modelMatch"], "confirmed")
        self.assertEqual(payload["status"], "ok")
        self.assertIsInstance(payload["durationMs"], int)
        self.assertEqual(payload["resultText"], "REVIEW_OK")
        brief = ask.call_args.args[0]
        self.assertIn("Purpose: review", brief)
        self.assertIn("Required write policy: patch_proposal", brief)
        self.assertIn("Identify concrete risks.", brief)

    def test_structured_context_is_snapshotted_before_invocation(self):
        working_dir, roots = self._workspace()
        context_name = "requirements.txt"
        expected_text = (Path(working_dir) / context_name).read_text(encoding="utf-8")
        result = router.AgentResult(
            "Claude",
            "claude-test",
            "OK",
            observed_models=("claude-test",),
        )
        with (
            patch.object(router, "ALLOWED_CONTEXT_ROOTS", roots),
            patch.object(router, "_ask_claude", return_value=result) as ask,
        ):
            router.run_agent(
                "claude",
                "Review.",
                working_dir=working_dir,
                context_files=[context_name],
                models={"claude": "claude-test"},
            )
        self.assertIn(expected_text.strip(), ask.call_args.args[0])
        self.assertIsNone(ask.call_args.args[4])

    def test_alias_is_not_falsely_confirmed(self):
        result = router.AgentResult(
            "Claude",
            "claude-opus-5",
            "UNTRUSTED_PROVIDER_TEXT",
            observed_models=("claude-opus-5",),
        )
        payload = router._structured_agent_payload("claude", "opus", result, 1)
        self.assertEqual(payload["modelMatch"], "mismatch")
        self.assertEqual(payload["status"], "invalid_output")
        self.assertNotIn("UNTRUSTED_PROVIDER_TEXT", payload["resultText"])
        self.assertIn("Response discarded", payload["resultText"])

    def test_panel_model_mismatch_is_not_counted_as_success(self):
        working_dir, roots = self._workspace()
        mismatch = router.AgentResult(
            "Claude",
            "claude-haiku-4-5",
            "UNTRUSTED_PROVIDER_TEXT",
            requested_model="claude-opus-5",
            observed_models=("claude-haiku-4-5",),
            exit_code=0,
        )
        with (
            patch.object(router, "ALLOWED_CONTEXT_ROOTS", roots),
            patch.object(router, "_ask_claude", return_value=mismatch),
        ):
            payload = json.loads(
                router.run_panel(
                    "Review.",
                    agent_ids=["claude"],
                    working_dir=working_dir,
                    models={"claude": "claude-opus-5"},
                )
            )
        self.assertEqual(payload["status"], "invalid_output")
        self.assertEqual(payload["results"][0]["status"], "invalid_output")
        self.assertEqual(payload["results"][0]["modelMatch"], "mismatch")
        self.assertNotIn("UNTRUSTED_PROVIDER_TEXT", payload["results"][0]["resultText"])

    def test_run_agent_rejects_direct_write_without_invocation(self):
        with patch.object(router, "_ask_claude") as ask:
            payload = json.loads(
                router.run_agent(
                    "claude",
                    "Edit the code.",
                    write_policy="isolated_write",
                )
            )
        self.assertEqual(payload["status"], "unsafe_request")
        self.assertEqual(payload["modelMatch"], "unverified")
        ask.assert_not_called()

    def test_run_agent_keeps_codex_startup_gate(self):
        with (
            patch.object(router, "CODEX_REVIEWER_ENABLED", False),
            patch.object(router, "_resolve_codex_command") as resolve,
            patch.object(router, "_run_agent_process") as run,
        ):
            payload = json.loads(router.run_agent("codex", "Review."))
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["modelMatch"], "unverified")
        resolve.assert_not_called()
        run.assert_not_called()

    def test_run_panel_keeps_antigravity_startup_gate(self):
        with (
            patch.object(router, "ANTIGRAVITY_REVIEWER_ENABLED", False),
            patch.object(router, "_resolve_command") as resolve,
            patch.object(router, "_run_agent_process") as run,
        ):
            payload = json.loads(router.run_panel("Review.", agent_ids=["antigravity"]))
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["results"][0]["status"], "unavailable")
        resolve.assert_not_called()
        run.assert_not_called()

    def test_run_agent_rejects_model_injection_before_process_start(self):
        working_dir, roots = self._workspace()
        with (
            patch.object(router, "ALLOWED_CONTEXT_ROOTS", roots),
            patch.object(router, "_resolve_command") as resolve,
            patch.object(router, "_run_agent_process") as run,
            self.assertRaises(ValueError),
        ):
            router.run_agent(
                "claude",
                "Review.",
                working_dir=working_dir,
                models={"claude": "safe&echo.INJECTED"},
            )
        resolve.assert_not_called()
        run.assert_not_called()

    def test_run_panel_defaults_are_parallel_and_opt_in_agents_stay_off(self):
        working_dir, roots = self._workspace()
        barrier = threading.Barrier(2)

        def claude(*args, **kwargs):
            del args, kwargs
            barrier.wait(timeout=2)
            return router.AgentResult(
                "Claude", "claude-test", "CLAUDE_OK", observed_models=("claude-test",)
            )

        def copilot(*args, **kwargs):
            del args, kwargs
            barrier.wait(timeout=2)
            return router.AgentResult(
                "Copilot", "gpt-test", "COPILOT_OK", observed_models=("gpt-test",)
            )

        with (
            patch.object(router, "ALLOWED_CONTEXT_ROOTS", roots),
            patch.object(router, "_ask_claude", side_effect=claude),
            patch.object(router, "_ask_copilot", side_effect=copilot),
            patch.object(router, "_ask_codex") as codex,
            patch.object(router, "_ask_antigravity") as antigravity,
            patch.object(router, "_ask_lm_studio") as lm_studio,
        ):
            payload = json.loads(
                router.run_panel("Review.", working_dir=working_dir, timeout_sec=10)
            )
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            [item["agentId"] for item in payload["results"]],
            ["claude", "copilot"],
        )
        codex.assert_not_called()
        antigravity.assert_not_called()
        lm_studio.assert_not_called()

    def test_run_panel_preflights_every_model_before_any_process(self):
        working_dir, roots = self._workspace()
        with (
            patch.object(router, "ALLOWED_CONTEXT_ROOTS", roots),
            patch.object(router, "_ask_claude") as claude,
            patch.object(router, "_ask_copilot") as copilot,
            patch.object(router, "_run_agent_process") as run,
            self.assertRaises(ValueError),
        ):
            router.run_panel(
                "Review.",
                agent_ids=["claude", "copilot"],
                working_dir=working_dir,
                models={"claude": "claude-safe", "copilot": "safe&echo.INJECTED"},
            )
        claude.assert_not_called()
        copilot.assert_not_called()
        run.assert_not_called()

    def test_run_panel_preflights_context_before_any_process(self):
        working_dir, roots = self._workspace()
        with (
            patch.object(router, "ALLOWED_CONTEXT_ROOTS", roots),
            patch.object(router, "_ask_claude") as claude,
            patch.object(router, "_ask_copilot") as copilot,
            patch.object(router, "_run_agent_process") as run,
            self.assertRaises(FileNotFoundError),
        ):
            router.run_panel(
                "Review.",
                working_dir=working_dir,
                context_files=["definitely-missing-context.txt"],
            )
        claude.assert_not_called()
        copilot.assert_not_called()
        run.assert_not_called()

    def test_structured_result_redacts_content_and_error(self):
        with patch.dict(
            router.os.environ,
            {"EXAMPLE_API_KEY": "configured-secret"},
            clear=False,
        ):
            payload = router._structured_agent_payload(
                "claude",
                "configured-secret",
                router.AgentResult(
                    "Claude",
                    "unknown",
                    "stdout configured-secret token=inline-secret",
                    status="execution_failed",
                    observed_models=("configured-secret",),
                    error_message="stderr Bearer bearer-secret",
                ),
                2,
            )
        rendered = json.dumps(payload)
        self.assertNotIn("configured-secret", rendered)
        self.assertNotIn("inline-secret", rendered)
        self.assertNotIn("bearer-secret", rendered)
        self.assertEqual(payload["modelMatch"], "confirmed")

    def test_doctor_redacts_secrets_and_does_not_report_executable_paths(self):
        secret = "doctor-secret-value"
        lm_result = {
            "provider": "lmstudio",
            "status": "unavailable",
            "configuredModelAvailable": False,
            "models": [],
            "warnings": [f"Bearer {secret}"],
        }
        with (
            patch.dict(router.os.environ, {"DOCTOR_API_KEY": secret}, clear=False),
            patch.object(
                router,
                "_doctor_agent_records",
                return_value=[
                    {"agentId": "claude", "status": "available", "version": "1.0"}
                ],
            ),
            patch.object(router, "_lm_studio_models_result", return_value=lm_result),
        ):
            rendered = router.doctor()
        self.assertNotIn(secret, rendered)
        self.assertNotIn("command", rendered.lower())
        self.assertNotIn("executable", rendered.lower())
        self.assertEqual(json.loads(rendered)["status"], "ok")


if __name__ == "__main__":
    unittest.main()
