"""Shared MCP router for local and CLI-backed advisory agents.

Tool-restricted reviewers and LM Studio receive only the prompt plus explicitly
allowed context. Codex and Antigravity CLI reviewers are disabled by default
because their available read tools cannot be configuration-independently confined.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import textwrap
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP


def _normalize_lm_studio_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if not normalized:
        raise ValueError("LM Studio base URL must not be empty")
    parsed = urllib.parse.urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("LM Studio base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError(
            "LM Studio credentials must be configured through the API key setting"
        )
    if parsed.query or parsed.fragment:
        raise ValueError(
            "LM Studio base URL must not contain a query string or fragment"
        )
    path = parsed.path.rstrip("/")
    if path not in {"", "/v1"}:
        raise ValueError("LM Studio base URL path must be empty or /v1")
    return f"{parsed.scheme}://{parsed.netloc}/v1"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _validate_lm_studio_transport(
    base_url: str,
    api_key: str,
    *,
    allow_insecure_remote: bool = False,
    allow_unauthenticated_remote: bool = False,
) -> None:
    parsed = urllib.parse.urlsplit(base_url)
    host = parsed.hostname or ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None

    if address is not None and address.is_unspecified:
        raise ValueError(
            "LM Studio base URL must be a client address, not a wildcard bind address"
        )

    is_loopback = host.lower() == "localhost" or bool(address and address.is_loopback)
    if is_loopback:
        return
    if parsed.scheme != "https" and not allow_insecure_remote:
        raise ValueError(
            "Remote LM Studio requires HTTPS. Set "
            "MULTI_AGENT_LM_STUDIO_ALLOW_INSECURE_REMOTE=1 only for an explicitly trusted network."
        )
    if not api_key and not allow_unauthenticated_remote:
        raise ValueError(
            "Remote LM Studio requires an API token. Set LM_API_TOKEN or "
            "MULTI_AGENT_LM_STUDIO_API_KEY."
        )


SERVER_ROOT = Path(__file__).resolve().parent
DEFAULT_TIMEOUT_SEC = int(os.environ.get("MULTI_AGENT_TIMEOUT_SEC", "300"))
DEFAULT_MAX_CHARS = int(os.environ.get("MULTI_AGENT_MAX_CHARS", "20000"))
DEFAULT_MAX_FILE_CHARS = int(os.environ.get("MULTI_AGENT_MAX_FILE_CHARS", "60000"))
MAX_TOTAL_CONTEXT_CHARS = 1_000_000
MAX_CONTEXT_FILES = 32
MAX_PROCESS_OUTPUT_BYTES = 8 * 1024 * 1024
LM_STUDIO_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
ANTIGRAVITY_MAX_PROMPT_CHARS = int(
    os.environ.get("MULTI_AGENT_ANTIGRAVITY_MAX_PROMPT_CHARS", "24000")
)
LM_STUDIO_BASE_URL = _normalize_lm_studio_base_url(
    os.environ.get("MULTI_AGENT_LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
)
LM_STUDIO_DEFAULT_MODEL = os.environ.get("MULTI_AGENT_LM_STUDIO_MODEL", "").strip()
LM_STUDIO_API_KEY = (
    os.environ.get("MULTI_AGENT_LM_STUDIO_API_KEY")
    or os.environ.get("LM_API_TOKEN", "")
).strip()
LM_STUDIO_MAX_TOKENS = int(os.environ.get("MULTI_AGENT_LM_STUDIO_MAX_TOKENS", "2048"))
LM_STUDIO_REASONING_EFFORT = os.environ.get(
    "MULTI_AGENT_LM_STUDIO_REASONING_EFFORT", "none"
).strip()
_validate_lm_studio_transport(
    LM_STUDIO_BASE_URL,
    LM_STUDIO_API_KEY,
    allow_insecure_remote=_env_flag("MULTI_AGENT_LM_STUDIO_ALLOW_INSECURE_REMOTE"),
    allow_unauthenticated_remote=_env_flag(
        "MULTI_AGENT_LM_STUDIO_ALLOW_UNAUTHENTICATED_REMOTE"
    ),
)
CODEX_REVIEWER_ENABLED = _env_flag("MULTI_AGENT_ENABLE_UNCONFINED_CODEX_REVIEWER")
ANTIGRAVITY_REVIEWER_ENABLED = _env_flag(
    "MULTI_AGENT_ENABLE_UNCONFINED_ANTIGRAVITY_REVIEWER"
)
_runtime_root_value = os.environ.get("MULTI_AGENT_RUNTIME_DIR", "").strip()
if _runtime_root_value:
    _runtime_candidate = Path(_runtime_root_value).expanduser()
    if not _runtime_candidate.is_absolute():
        raise ValueError("MULTI_AGENT_RUNTIME_DIR must be an absolute local path")
    RUNTIME_ROOT = _runtime_candidate.resolve()
else:
    RUNTIME_ROOT = (
        Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
        / "OpenAI"
        / "multi-agent-router"
    ).resolve()
if RUNTIME_ROOT == Path(RUNTIME_ROOT.anchor) or (
    os.name == "nt" and str(RUNTIME_ROOT).startswith("\\\\")
):
    raise ValueError("MULTI_AGENT_RUNTIME_DIR must not be a filesystem or UNC root")
if (
    RUNTIME_ROOT.name.lower() != "multi-agent-router"
    or RUNTIME_ROOT.parent.name.lower() != "openai"
):
    raise ValueError(
        "MULTI_AGENT_RUNTIME_DIR must be a dedicated <local path>/OpenAI/multi-agent-router directory"
    )
PROMPT_DIR = RUNTIME_ROOT / "prompts"
REVIEW_DIR = SERVER_ROOT / ".tmp" / "reviews"


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _reject_reparse_components(path: Path, label: str) -> None:
    if ".." in path.parts:
        raise PermissionError(f"{label} must not contain parent traversal")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if _is_reparse_point(current):
            raise PermissionError(f"{label} contains a reparse point: {current}")


def _load_allowed_roots(value: str) -> tuple[Path, ...]:
    if not value.strip():
        return ()
    try:
        raw_roots = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("MULTI_AGENT_ALLOWED_ROOTS_JSON must be a JSON array") from exc
    if not isinstance(raw_roots, list) or not all(
        isinstance(item, str) for item in raw_roots
    ):
        raise ValueError("MULTI_AGENT_ALLOWED_ROOTS_JSON must be a JSON array of paths")

    roots: list[Path] = []
    for raw_root in raw_roots:
        candidate = Path(raw_root).expanduser()
        if not candidate.is_absolute():
            raise ValueError("Every allowed context root must be an absolute path")
        _reject_reparse_components(candidate, "Allowed context root")
        try:
            root = candidate.resolve(strict=True)
        except OSError as exc:
            raise ValueError(
                f"Allowed context root does not exist: {candidate}"
            ) from exc
        if not root.is_dir():
            raise ValueError(f"Allowed context root is not a directory: {root}")
        if root == Path(root.anchor):
            raise ValueError("A filesystem root cannot be an allowed context root")
        if os.name == "nt" and str(root).startswith("\\\\"):
            raise ValueError("UNC paths cannot be allowed context roots")
        roots.append(root)
    return tuple(dict.fromkeys(roots))


ALLOWED_CONTEXT_ROOTS = _load_allowed_roots(
    os.environ.get("MULTI_AGENT_ALLOWED_ROOTS_JSON", "")
)

USER_HOME = Path.home()
NPM_BIN = USER_HOME / "AppData" / "Roaming" / "npm"
AGY_BIN = USER_HOME / "AppData" / "Local" / "agy" / "bin"
AGY_APPDATA = USER_HOME / ".gemini" / "antigravity-cli"
CODEX_APP_BIN_ROOT = USER_HOME / "AppData" / "Local" / "OpenAI" / "Codex" / "bin"


@dataclass(frozen=True)
class AgentResult:
    name: str
    model: str
    content: str
    status: str = "ok"
    requested_model: str | None = None
    observed_models: tuple[str, ...] = ()
    exit_code: int | None = None
    error_message: str | None = None

    def render(self) -> str:
        if self.requested_model and not self.observed_models:
            model_label = f"{self.requested_model} requested; actual unverified"
        else:
            model_label = self.model
        return _redact_secrets(
            f"## {self.name} (model: {model_label})\n\n{self.content}"
        )


class LMStudioError(RuntimeError):
    """Raised when the configured local LM Studio API cannot serve a request."""


_SECRET_ENV_NAME = re.compile(
    r"(?:^|_)(?:API_?KEY|AUTH_?TOKEN|ACCESS_?TOKEN|TOKEN|SECRET|PASSWORD|PASSWD)(?:$|_)",
    re.IGNORECASE,
)
_INLINE_SECRET_PATTERNS = (
    re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"""(?ix)
        (["'](?:api[_-]?key|auth[_-]?token|access[_-]?token|token|secret|password|passwd)["']
        \s*:\s*["'])
        ([^"']+)
        """,
    ),
    re.compile(
        r"""(?ix)
        (\b(?:api[_-]?key|auth[_-]?token|access[_-]?token|token|secret|password|passwd)\b
        \s*[:=]\s*["']?)
        ([^\s,"'}]+)
        """,
    ),
    re.compile(r"(?i)(https?://[^/\s:@]+:)[^@\s/]+(?=@)"),
)


def _redact_secrets(value: str) -> str:
    """Redact configured credentials and common inline secret forms from text."""
    redacted = value
    secret_values = {
        item
        for name, item in os.environ.items()
        if _SECRET_ENV_NAME.search(name) and len(item) >= 6
    }
    if LM_STUDIO_API_KEY:
        secret_values.add(LM_STUDIO_API_KEY)
    for secret in sorted(secret_values, key=len, reverse=True):
        redacted = redacted.replace(secret, "[redacted]")
    for pattern in _INLINE_SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[redacted]", redacted)
    return redacted


SERVER_INSTRUCTIONS = (
    "Use this server to ask local external coding agents for second opinions. "
    "Treat responses as advisory only. Codex owns final decisions, code edits, "
    "validation, and user-facing conclusions. Context files are accepted only "
    "under machine-local administrator-approved roots. The Codex CLI reviewer "
    "is disabled unless the administrator explicitly opts into its unconfined reads."
)

mcp = FastMCP("multi-agent-router", instructions=SERVER_INSTRUCTIONS)


_BASE_CHILD_ENV_NAMES = (
    "ALLUSERSPROFILE",
    "APPDATA",
    "CODEX_HOME",
    "COMSPEC",
    "HOMEDRIVE",
    "HOMEPATH",
    "LANG",
    "LC_ALL",
    "LOCALAPPDATA",
    "NO_COLOR",
    "OS",
    "PATH",
    "PATHEXT",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "USERPROFILE",
    "WINDIR",
)


def _augmented_env(allowed_auth_env_names: Sequence[str] = ()) -> dict[str, str]:
    allowed_names = set(_BASE_CHILD_ENV_NAMES) | set(allowed_auth_env_names)
    env = {
        name: value
        for name, value in os.environ.items()
        if name.upper() in allowed_names
    }
    extra_paths = [str(NPM_BIN), str(AGY_BIN)]
    env["PATH"] = os.pathsep.join(extra_paths + [env.get("PATH", "")])
    env.setdefault("NO_COLOR", "1")
    return env


def _resolve_command(
    env_name: str, fallback_names: Iterable[str], fallback_path: Path | None = None
) -> str:
    configured = os.environ.get(env_name)
    if configured:
        return configured

    if fallback_path and fallback_path.exists():
        return str(fallback_path)

    search_path = os.pathsep.join(
        [str(NPM_BIN), str(AGY_BIN), os.environ.get("PATH", "")]
    )
    for name in fallback_names:
        found = shutil.which(name, path=search_path)
        if found:
            return found

    names = ", ".join(fallback_names)
    raise FileNotFoundError(f"Could not find command for {env_name}. Tried: {names}")


def _version_tuple(command: str) -> tuple[int, ...]:
    try:
        completed = subprocess.run(
            [command, "--version"],
            check=False,
            env=_augmented_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    match = re.search(r"\d+(?:\.\d+)+", completed.stdout + completed.stderr)
    return tuple(int(part) for part in match.group(0).split(".")) if match else ()


def _resolve_codex_command() -> str:
    configured = os.environ.get("MULTI_AGENT_CODEX_CMD")
    if configured:
        return configured

    candidates: list[str] = []
    npm_codex = NPM_BIN / "codex.cmd"
    if npm_codex.exists():
        candidates.append(str(npm_codex))
    if CODEX_APP_BIN_ROOT.exists():
        candidates.extend(str(path) for path in CODEX_APP_BIN_ROOT.glob("*/codex.exe"))
    found = shutil.which("codex", path=_augmented_env().get("PATH"))
    if found:
        candidates.append(found)

    unique_candidates = list(dict.fromkeys(candidates))
    usable = [(candidate, _version_tuple(candidate)) for candidate in unique_candidates]
    usable = [(candidate, version) for candidate, version in usable if version]
    if not usable:
        raise FileNotFoundError("Could not find a usable Codex CLI")
    return max(usable, key=lambda item: item[1])[0]


def _normalize_working_dir(working_dir: str | None) -> str:
    if not working_dir:
        return str(SERVER_ROOT)

    candidate = Path(working_dir).expanduser()
    if not candidate.is_absolute():
        raise ValueError("working_dir must be an absolute path")
    _reject_reparse_components(candidate, "working_dir")
    try:
        path = candidate.resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError(f"working_dir does not exist: {candidate}") from exc
    if not path.is_dir():
        raise NotADirectoryError(f"working_dir is not a directory: {path}")
    if not any(
        path == root or path.is_relative_to(root) for root in ALLOWED_CONTEXT_ROOTS
    ):
        raise PermissionError(
            "working_dir is outside MULTI_AGENT_ALLOWED_ROOTS_JSON; "
            "rerun install.ps1 with -AllowedRoot and restart Codex"
        )
    return str(path)


def _validate_context_path_components(root: Path, path: Path) -> None:
    current = root
    if _is_reparse_point(current):
        raise PermissionError(f"Allowed context root is a reparse point: {root}")
    for part in path.relative_to(root).parts:
        current /= part
        if _is_reparse_point(current):
            raise PermissionError(f"Context path contains a reparse point: {current}")


def _allowed_root_for(path: Path) -> Path | None:
    matches = [
        root
        for root in ALLOWED_CONTEXT_ROOTS
        if path == root or path.is_relative_to(root)
    ]
    return max(matches, key=lambda item: len(item.parts)) if matches else None


def _context_from_files(
    working_dir: str, context_files: Sequence[str] | None, max_file_chars: int
) -> str:
    if not context_files:
        return ""
    if len(context_files) > MAX_CONTEXT_FILES:
        raise ValueError(f"context_files accepts at most {MAX_CONTEXT_FILES} files")

    cwd = Path(working_dir).resolve(strict=True)
    cwd_root = _allowed_root_for(cwd)
    if cwd_root is None:
        raise PermissionError(
            "context_files are disabled until MULTI_AGENT_ALLOWED_ROOTS_JSON is configured"
        )
    _validate_context_path_components(cwd_root, cwd)
    sections: list[str] = []
    total_chars = 0
    for raw_path in context_files:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            raise ValueError("context_files entries must be relative to working_dir")
        if os.name == "nt" and ":" in raw_path:
            raise ValueError(
                "context_files entries must not use alternate data streams"
            )
        try:
            lexical_path = cwd / candidate
            _reject_reparse_components(lexical_path, "Context path")
            path = lexical_path.resolve(strict=True)
            if not path.is_relative_to(cwd):
                raise PermissionError(f"Context path escapes working_dir: {raw_path}")
            root = _allowed_root_for(path)
            if root is None:
                raise PermissionError(
                    f"Context path is outside allowed roots: {raw_path}"
                )
            _validate_context_path_components(root, path)
            if not path.is_file():
                raise ValueError(f"Context path is not a regular file: {raw_path}")
            with path.open(encoding="utf-8", errors="replace") as handle:
                text = handle.read(max_file_chars + 1)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Context file does not exist: {raw_path}") from exc

        if len(text) > max_file_chars:
            text = text[:max_file_chars] + "\n\n[truncated]"
        total_chars += len(text)
        if total_chars > MAX_TOTAL_CONTEXT_CHARS:
            raise ValueError(
                "Combined context files exceed the 1,000,000 character limit"
            )
        display_path = path.relative_to(cwd)
        sections.append(f"### {display_path}\n\n```text\n{text}\n```")

    return "\n\n".join(sections)


_SAFE_CLI_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,199}$")


def _validate_cli_model(model: str | None) -> None:
    if model is not None and not _SAFE_CLI_MODEL.fullmatch(model):
        raise ValueError(
            "CLI model must use only letters, digits, dot, underscore, colon, slash, "
            "at sign, plus, or hyphen (maximum 200 characters)"
        )


def _require_native_prompt_command(command: str) -> None:
    resolved = shutil.which(command, path=_augmented_env().get("PATH")) or command
    if Path(resolved).suffix.lower() in {".cmd", ".bat"}:
        raise ValueError(
            "Antigravity prompt transport requires a native executable, not a .cmd/.bat wrapper"
        )


def _readonly_prompt(
    prompt: str,
    working_dir: str,
    context_files: Sequence[str] | None = None,
    max_file_chars: int = DEFAULT_MAX_FILE_CHARS,
) -> str:
    context = _context_from_files(working_dir, context_files, max_file_chars)
    context_block = f"\n\nContext files:\n{context}" if context else ""

    return _redact_secrets(
        textwrap.dedent(
            f"""
        You are being consulted by Codex as an external reviewer.

        Operating rules:
        - Work read-only. Do not modify files, create commits, install packages, or run destructive commands.
        - If you need more context, say exactly what context is missing.
        - Keep the answer concise, concrete, and grounded in the supplied prompt.
        - If the request asks for an exact test string, return that exact string.
        - Codex will make the final decision and perform any implementation.

        Authorized review context: only the prompt and embedded context files below.
        Do not access other local files even if the CLI permission layer would allow it.

        User/Codex request:
        {prompt}{context_block}
        """
        ).strip()
    )


def _write_prompt_file(prompt: str) -> Path:
    request_dir = PROMPT_DIR / uuid.uuid4().hex
    request_dir.mkdir(parents=True, exist_ok=False)
    path = request_dir / "request.txt"
    path.write_text(prompt, encoding="utf-8")
    return path


def _create_review_dir() -> Path:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="review-", dir=REVIEW_DIR))


def _remove_review_dir(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except OSError:
        pass


def _remove_prompt_file(path: Path) -> None:
    try:
        path.unlink()
        path.parent.rmdir()
    except OSError:
        pass


def _run_agent_process(
    command: list[str],
    working_dir: str,
    timeout_sec: int,
    stdin_text: str | None = None,
    allowed_auth_env_names: Sequence[str] = (),
) -> subprocess.CompletedProcess[str]:
    popen_kwargs = {
        "cwd": working_dir,
        "env": _augmented_env(allowed_auth_env_names),
        "stdin": subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    process = subprocess.Popen(command, **popen_kwargs)
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    output_limit_exceeded = threading.Event()
    termination_lock = threading.Lock()

    def drain(stream, buffer: bytearray) -> None:
        try:
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                remaining = MAX_PROCESS_OUTPUT_BYTES + 1 - len(buffer)
                if remaining > 0:
                    buffer.extend(chunk[:remaining])
                if len(buffer) > MAX_PROCESS_OUTPUT_BYTES or len(chunk) > remaining:
                    with termination_lock:
                        if not output_limit_exceeded.is_set():
                            output_limit_exceeded.set()
                            _terminate_process_tree(process)
        finally:
            stream.close()

    stdout_thread = threading.Thread(
        target=drain, args=(process.stdout, stdout_buffer), daemon=True
    )
    stderr_thread = threading.Thread(
        target=drain, args=(process.stderr, stderr_buffer), daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()

    stdin_thread: threading.Thread | None = None
    if stdin_text is not None:

        def write_stdin() -> None:
            try:
                process.stdin.write(stdin_text.encode("utf-8"))
                process.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            finally:
                process.stdin.close()

        stdin_thread = threading.Thread(target=write_stdin, daemon=True)
        stdin_thread.start()

    timed_out = False
    try:
        process.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        process.wait()

    stdout_thread.join()
    stderr_thread.join()
    if stdin_thread is not None:
        stdin_thread.join(timeout=1)
    stdout = bytes(stdout_buffer[:MAX_PROCESS_OUTPUT_BYTES]).decode(
        "utf-8", errors="replace"
    )
    stderr = bytes(stderr_buffer[:MAX_PROCESS_OUTPUT_BYTES]).decode(
        "utf-8", errors="replace"
    )
    if timed_out:
        raise subprocess.TimeoutExpired(
            command, timeout_sec, output=stdout, stderr=stderr
        )
    if output_limit_exceeded.is_set():
        raise subprocess.SubprocessError(
            "Reviewer output exceeded the 8 MiB safety limit"
        )
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        taskkill = Path(system_root) / "System32" / "taskkill.exe"
        if taskkill.is_file():
            try:
                subprocess.run(
                    [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except (OSError, subprocess.SubprocessError):
                pass
    if process.poll() is None:
        process.kill()


def _process_output(completed: subprocess.CompletedProcess[str], max_chars: int) -> str:

    output = "\n".join(
        part for part in [completed.stdout.strip(), completed.stderr.strip()] if part
    ).strip()
    if not output:
        output = f"(no output; exit code {completed.returncode})"

    if completed.returncode != 0:
        output = f"Command failed with exit code {completed.returncode}.\n\n{output}"

    output = _redact_secrets(output)
    if len(output) > max_chars:
        output = output[:max_chars] + "\n\n[truncated]"
    return output


def _run_agent(
    command: list[str],
    working_dir: str,
    timeout_sec: int,
    max_chars: int,
    stdin_text: str | None = None,
) -> str:
    completed = _run_agent_process(command, working_dir, timeout_sec, stdin_text)
    return _process_output(completed, max_chars)


def _jsonl_records(text: str) -> list[dict]:
    records: list[dict] = []
    for raw_line in text.splitlines():
        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _lm_studio_headers() -> dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if LM_STUDIO_API_KEY:
        headers["Authorization"] = f"Bearer {LM_STUDIO_API_KEY}"
    return headers


def _redact_lm_studio_secrets(value: str) -> str:
    return _redact_secrets(value)


def _lm_studio_error_detail(raw_body: str) -> str:
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, str) and error.strip():
            return _redact_lm_studio_secrets(error.strip())
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return _redact_lm_studio_secrets(error["message"].strip())
    compact = " ".join(raw_body.split())
    return _redact_lm_studio_secrets(compact[:500]) or "no error detail returned"


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_limited_http_body(stream) -> str:
    raw = stream.read(LM_STUDIO_MAX_RESPONSE_BYTES + 1)
    if len(raw) > LM_STUDIO_MAX_RESPONSE_BYTES:
        raise LMStudioError("LM Studio response exceeded the 8 MiB safety limit")
    return raw.decode("utf-8", errors="replace")


def _lm_studio_json_request(
    method: str,
    path: str,
    payload: dict | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict:
    normalized_path = path.lstrip("/")
    if normalized_path.startswith("api/"):
        server_root = LM_STUDIO_BASE_URL.removesuffix("/v1")
        url = f"{server_root}/{normalized_path}"
    else:
        url = f"{LM_STUDIO_BASE_URL}/{normalized_path}"
    data = (
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if payload is not None
        else None
    )
    request = urllib.request.Request(
        url,
        data=data,
        headers=_lm_studio_headers(),
        method=method.upper(),
    )
    try:
        opener = urllib.request.build_opener(_RejectRedirectHandler())
        with opener.open(request, timeout=timeout_sec) as response:
            raw_body = _read_limited_http_body(response)
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            raise LMStudioError("LM Studio redirects are not allowed") from exc
        raw_body = _read_limited_http_body(exc)
        detail = _lm_studio_error_detail(raw_body)
        raise LMStudioError(f"LM Studio returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LMStudioError(
            f"Could not reach LM Studio at {LM_STUDIO_BASE_URL}: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise LMStudioError(
            f"LM Studio request timed out after {timeout_sec} seconds at {LM_STUDIO_BASE_URL}"
        ) from exc

    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise LMStudioError("LM Studio returned a non-JSON response") from exc
    if not isinstance(parsed, dict):
        raise LMStudioError("LM Studio returned an unexpected JSON response")
    if "error" in parsed:
        detail = _lm_studio_error_detail(raw_body)
        raise LMStudioError(f"LM Studio returned an API error: {detail}")
    return parsed


def _lm_studio_models_result(timeout_sec: int = 15) -> dict:
    """Merge LM Studio native metadata with its OpenAI-compatible model IDs."""
    warnings: list[str] = []
    native_payload: dict | None = None
    compatible_payload: dict | None = None
    try:
        native_payload = _lm_studio_json_request(
            "GET", "api/v1/models", timeout_sec=timeout_sec
        )
    except LMStudioError as exc:
        warnings.append(f"Native model list failed: {_redact_secrets(str(exc))}")
    try:
        compatible_payload = _lm_studio_json_request(
            "GET", "models", timeout_sec=timeout_sec
        )
    except LMStudioError as exc:
        warnings.append(
            f"OpenAI-compatible model list failed: {_redact_secrets(str(exc))}"
        )

    raw_native = native_payload.get("models") if native_payload else None
    native_valid = isinstance(raw_native, list)
    if native_payload is not None and not native_valid:
        warnings.append("Native model list returned an unexpected schema.")

    raw_compatible = compatible_payload.get("data") if compatible_payload else None
    compatible_valid = isinstance(raw_compatible, list)
    if compatible_payload is not None and not compatible_valid:
        warnings.append("OpenAI-compatible model list returned an unexpected schema.")

    base_result = {
        "provider": "lmstudio",
        "baseUrl": LM_STUDIO_BASE_URL.removesuffix("/v1"),
        "openAIBaseUrl": LM_STUDIO_BASE_URL,
        "configuredModel": LM_STUDIO_DEFAULT_MODEL or None,
    }
    if not native_valid and not compatible_valid:
        return {
            **base_result,
            "status": "unavailable",
            "configuredModelAvailable": False,
            "models": [],
            "warnings": warnings,
            "errorMessage": "; ".join(warnings) or "No model endpoint was available.",
        }

    metadata_by_id: dict[str, dict] = {}
    candidate_ids: dict[str, None] = {}
    if compatible_valid:
        for index, item in enumerate(raw_compatible):
            if not isinstance(item, dict):
                warnings.append(
                    f"OpenAI-compatible model entry {index} was not an object and was ignored."
                )
                continue
            model_id = item.get("id")
            if isinstance(model_id, str) and model_id.strip():
                candidate_ids[model_id.strip()] = None

    if native_valid:
        for index, item in enumerate(raw_native):
            if not isinstance(item, dict):
                warnings.append(
                    f"Native model entry {index} was not an object and was ignored."
                )
                continue
            key = item.get("key")
            if not isinstance(key, str) or not key.strip():
                continue
            key = key.strip()
            loaded_raw = item.get("loaded_instances", [])
            if not isinstance(loaded_raw, list):
                warnings.append(
                    f"Native model entry {index} had invalid loaded_instances metadata."
                )
                loaded_raw = []
            loaded_ids = [
                loaded_id.strip()
                for instance in loaded_raw
                if isinstance(instance, dict)
                and isinstance(instance.get("id"), str)
                and (loaded_id := instance["id"]).strip()
            ]
            variants_raw = item.get("variants", [])
            if not isinstance(variants_raw, list):
                warnings.append(
                    f"Native model entry {index} had invalid variants metadata."
                )
                variants_raw = []
            variants = [
                variant.strip()
                for variant in variants_raw
                if isinstance(variant, str) and variant.strip()
            ]
            normalized = {**item, "key": key, "loaded_ids": loaded_ids}
            for model_id in (key, *loaded_ids, *variants):
                metadata_by_id[model_id] = normalized
            if item.get("type") == "llm":
                candidate_ids[key] = None
                for model_id in loaded_ids:
                    candidate_ids[model_id] = None

    models: list[dict] = []
    for model_id in candidate_ids:
        metadata = metadata_by_id.get(model_id, {})
        if metadata.get("type") == "embedding":
            continue
        loaded_ids = metadata.get("loaded_ids", [])
        quantization = metadata.get("quantization")
        capabilities = metadata.get("capabilities")
        models.append(
            {
                "id": model_id,
                "key": metadata.get("key"),
                "displayName": metadata.get("display_name") or model_id,
                "loaded": model_id in loaded_ids
                or bool(metadata.get("key") == model_id and loaded_ids),
                "isDefault": model_id == LM_STUDIO_DEFAULT_MODEL,
                "params": metadata.get("params_string"),
                "quantization": (
                    quantization.get("name") if isinstance(quantization, dict) else None
                ),
                "maxContextLength": (
                    metadata.get("max_context_length")
                    if isinstance(metadata.get("max_context_length"), (int, float))
                    else None
                ),
                "trainedForToolUse": (
                    capabilities.get("trained_for_tool_use")
                    if isinstance(capabilities, dict)
                    and isinstance(capabilities.get("trained_for_tool_use"), bool)
                    else None
                ),
                "vision": (
                    capabilities.get("vision")
                    if isinstance(capabilities, dict)
                    and isinstance(capabilities.get("vision"), bool)
                    else None
                ),
                "loadedInstanceIds": list(loaded_ids),
                "variants": [
                    variant
                    for variant in metadata.get("variants", [])
                    if isinstance(variant, str) and variant.strip()
                ],
            }
        )
    models.sort(
        key=lambda item: (
            not item["isDefault"],
            not item["loaded"],
            item["id"].lower(),
        )
    )
    return {
        **base_result,
        "status": "available",
        "configuredModelAvailable": bool(
            LM_STUDIO_DEFAULT_MODEL
            and any(item["id"] == LM_STUDIO_DEFAULT_MODEL for item in models)
        ),
        "models": models,
        "warnings": warnings,
    }


def _lm_studio_model_ids(timeout_sec: int = 15) -> list[str]:
    result = _lm_studio_models_result(timeout_sec)
    if result["status"] != "available":
        raise LMStudioError(
            result.get("errorMessage", "LM Studio model list unavailable")
        )
    return [item["id"] for item in result["models"]]


def _extract_lm_studio_chat_response(
    payload: dict,
) -> tuple[str | None, str | None, str | None]:
    actual_model = payload.get("model")
    if not isinstance(actual_model, str) or not actual_model.strip():
        actual_model = None

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None, actual_model, None
    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    finish_reason = finish_reason if isinstance(finish_reason, str) else None
    message = choice.get("message")
    if not isinstance(message, dict):
        return None, actual_model, finish_reason

    content = message.get("content")
    if isinstance(content, str):
        answer = content.strip()
    elif isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str):
                text_parts.append(text)
            elif isinstance(text, dict) and isinstance(text.get("value"), str):
                text_parts.append(text["value"])
        answer = "".join(text_parts).strip()
    else:
        answer = ""
    return answer or None, actual_model, finish_reason


def _agent_failure(
    name: str,
    requested_model: str | None,
    completed: subprocess.CompletedProcess[str],
    max_chars: int,
    actual_model: str | None = None,
) -> AgentResult:
    model_label = actual_model or (
        f"{requested_model} requested; actual unavailable"
        if requested_model
        else "unknown"
    )
    return AgentResult(
        name,
        model_label,
        _process_output(completed, max_chars),
        status="execution_failed",
        requested_model=requested_model,
        observed_models=(actual_model,) if actual_model else (),
        exit_code=completed.returncode,
        error_message=f"{name} exited with code {completed.returncode}.",
    )


def _latest_antigravity_transcript(
    start_time: float, run_marker: str | None = None
) -> Path | None:
    brain_root = AGY_APPDATA / "brain"
    if not brain_root.exists():
        return None

    candidates: list[Path] = []
    for pattern in (
        "*/.system_generated/logs/transcript_full.jsonl",
        "*/.system_generated/logs/transcript.jsonl",
    ):
        for path in brain_root.glob(pattern):
            try:
                if path.stat().st_mtime >= start_time - 5:
                    candidates.append(path)
            except OSError:
                continue
    if run_marker:
        matching: list[Path] = []
        for path in candidates:
            try:
                if run_marker in path.read_text(encoding="utf-8", errors="replace"):
                    matching.append(path)
            except OSError:
                continue
        candidates = matching
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _extract_antigravity_details(transcript: Path) -> tuple[str | None, str | None]:
    last_model_content: str | None = None
    model_name: str | None = None
    try:
        with transcript.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                raw_model = (
                    record.get("model")
                    or record.get("model_name")
                    or record.get("modelName")
                )
                if isinstance(raw_model, str) and raw_model.strip():
                    model_name = raw_model.strip()
                content = record.get("content")
                if record.get("source") == "USER_EXPLICIT" and isinstance(content, str):
                    match = re.search(
                        r"changed setting `Model Selection` from .*? to (.+?)\. No need",
                        content,
                    )
                    if match:
                        model_name = match.group(1).strip()
                if record.get("source") == "MODEL" and isinstance(
                    record.get("content"), str
                ):
                    last_model_content = record["content"].strip()
    except OSError:
        return None, None
    return last_model_content, model_name


def _parse_codex_output(stdout: str) -> str | None:
    answer: str | None = None
    for record in _jsonl_records(stdout):
        if record.get("type") != "item.completed":
            continue
        item = record.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            text = item.get("text")
            if isinstance(text, str):
                answer = text.strip()
    return answer


def _codex_default_model(codex: str) -> str | None:
    try:
        completed = _run_agent_process(
            [codex, "doctor", "--json"], str(SERVER_ROOT), 45
        )
        report = json.loads(completed.stdout)
        return report["checks"]["config.load"]["details"]["model"]
    except (
        OSError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
    ):
        return None


def _parse_claude_output_details(
    stdout: str,
) -> tuple[str | None, str | None, tuple[str, ...]]:
    answer: str | None = None
    model: str | None = None
    observed_models: list[str] = []
    for record in _jsonl_records(stdout):
        if record.get("type") == "system" and isinstance(record.get("model"), str):
            model = record["model"]
        if record.get("type") == "assistant":
            message = record.get("message")
            if isinstance(message, dict):
                if isinstance(message.get("model"), str):
                    model = message["model"]
                content = message.get("content")
                if isinstance(content, list):
                    text_parts = [
                        part["text"]
                        for part in content
                        if isinstance(part, dict)
                        and part.get("type") == "text"
                        and isinstance(part.get("text"), str)
                    ]
                    if text_parts:
                        answer = "".join(text_parts).strip()
        if record.get("type") == "result" and isinstance(record.get("result"), str):
            answer = record["result"].strip()
        model_usage = record.get("modelUsage")
        if isinstance(model_usage, dict):
            observed_models.extend(
                key.strip()
                for key in model_usage
                if isinstance(key, str) and key.strip()
            )
    if model:
        observed_models.append(model)
    return answer, model, tuple(dict.fromkeys(observed_models))


def _parse_claude_output(stdout: str) -> tuple[str | None, str | None]:
    answer, model, _ = _parse_claude_output_details(stdout)
    return answer, model


def _parse_copilot_output(stdout: str) -> tuple[str | None, str | None]:
    answer: str | None = None
    model: str | None = None
    for record in _jsonl_records(stdout):
        data = record.get("data")
        if (
            record.get("type") == "session.tools_updated"
            and isinstance(data, dict)
            and isinstance(data.get("model"), str)
        ):
            model = data["model"]
        if record.get("type") == "assistant.message" and isinstance(data, dict):
            if isinstance(data.get("model"), str):
                model = data["model"]
            if isinstance(data.get("content"), str):
                answer = data["content"].strip()
    return answer, model


def _ask_codex(
    prompt: str,
    working_dir: str,
    timeout_sec: int,
    max_chars: int,
    context_files: Sequence[str] | None = None,
    model: str | None = None,
) -> AgentResult:
    if not CODEX_REVIEWER_ENABLED:
        return AgentResult(
            "Codex",
            model or "disabled",
            "Codex CLI reviewer is disabled by policy because its read-only sandbox "
            "does not confine file reads. An administrator may opt in at MCP startup "
            "with MULTI_AGENT_ENABLE_UNCONFINED_CODEX_REVIEWER=1.",
            status="unavailable",
            requested_model=model,
            error_message="Codex reviewer is disabled by startup policy.",
        )
    _validate_cli_model(model)
    codex = _resolve_codex_command()
    command = [codex]
    if model:
        command.extend(["--model", model])
    command.extend(
        [
            "--ask-for-approval",
            "never",
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--json",
            "-",
        ]
    )
    full_prompt = _readonly_prompt(prompt, working_dir, context_files)
    review_dir = _create_review_dir()
    try:
        completed = _run_agent_process(
            command,
            str(review_dir),
            timeout_sec,
            stdin_text=full_prompt,
            allowed_auth_env_names=("OPENAI_API_KEY",),
        )
        answer = _parse_codex_output(completed.stdout)
        actual_model = model or _codex_default_model(codex) or "unknown"
        if completed.returncode != 0 or not answer:
            return _agent_failure("Codex", model or actual_model, completed, max_chars)
        return AgentResult(
            "Codex",
            actual_model,
            _redact_secrets(answer[:max_chars]),
            requested_model=model,
            exit_code=completed.returncode,
        )
    finally:
        _remove_review_dir(review_dir)


def _ask_claude(
    prompt: str,
    working_dir: str,
    timeout_sec: int,
    max_chars: int,
    context_files: Sequence[str] | None = None,
    model: str | None = None,
) -> AgentResult:
    _validate_cli_model(model)
    claude = _resolve_command(
        "MULTI_AGENT_CLAUDE_CMD",
        ["claude.cmd", "claude"],
        NPM_BIN / "claude.cmd",
    )
    command = [
        claude,
        "--print",
        "--permission-mode",
        "plan",
        "--safe-mode",
        "--no-session-persistence",
        "--tools",
        "",
        "--verbose",
        "--output-format",
        "stream-json",
    ]
    if model:
        command.extend(["--model", model])
    full_prompt = _readonly_prompt(prompt, working_dir, context_files)
    review_dir = _create_review_dir()
    try:
        completed = _run_agent_process(
            command,
            str(review_dir),
            timeout_sec,
            stdin_text=full_prompt,
            allowed_auth_env_names=("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
        )
        answer, actual_model, observed_models = _parse_claude_output_details(
            completed.stdout
        )
        if completed.returncode != 0 or not answer:
            return _agent_failure("Claude", model, completed, max_chars, actual_model)
        return AgentResult(
            "Claude",
            actual_model or model or "unknown",
            _redact_secrets(answer[:max_chars]),
            requested_model=model,
            observed_models=observed_models,
            exit_code=completed.returncode,
        )
    finally:
        _remove_review_dir(review_dir)


def _ask_copilot(
    prompt: str,
    working_dir: str,
    timeout_sec: int,
    max_chars: int,
    context_files: Sequence[str] | None = None,
    model: str | None = None,
) -> AgentResult:
    _validate_cli_model(model)
    copilot = _resolve_command(
        "MULTI_AGENT_COPILOT_CMD",
        ["copilot.cmd", "copilot"],
        NPM_BIN / "copilot.cmd",
    )
    full_prompt = _readonly_prompt(prompt, working_dir, context_files)
    prompt_file: Path | None = None
    try:
        prompt_file = _write_prompt_file(full_prompt)
        command = [
            copilot,
            "--prompt",
            "Open request.txt with the view tool, follow its operating rules, and answer it.",
            "--output-format",
            "json",
            "--silent",
        ]
        command.extend(
            [
                "--mode",
                "plan",
                "--available-tools=view",
                "--disable-builtin-mcps",
                "--disallow-temp-dir",
                "--no-custom-instructions",
                "--no-remote",
                "--no-remote-export",
                "--no-auto-update",
                "--secret-env-vars=LM_API_TOKEN,MULTI_AGENT_LM_STUDIO_API_KEY",
            ]
        )
        if model:
            command.extend(["--model", model])
        completed = _run_agent_process(
            command,
            str(prompt_file.parent),
            timeout_sec,
            allowed_auth_env_names=(
                "COPILOT_GITHUB_TOKEN",
                "GH_TOKEN",
                "GITHUB_TOKEN",
            ),
        )
        answer, actual_model = _parse_copilot_output(completed.stdout)
        if completed.returncode != 0 or not answer:
            return _agent_failure("Copilot", model, completed, max_chars, actual_model)
        return AgentResult(
            "Copilot",
            actual_model or model or "unknown",
            _redact_secrets(answer[:max_chars]),
            requested_model=model,
            observed_models=(actual_model,) if actual_model else (),
            exit_code=completed.returncode,
        )
    finally:
        if prompt_file:
            _remove_prompt_file(prompt_file)


def _ask_antigravity(
    prompt: str,
    working_dir: str,
    timeout_sec: int,
    max_chars: int,
    context_files: Sequence[str] | None = None,
    model: str | None = None,
) -> AgentResult:
    if not ANTIGRAVITY_REVIEWER_ENABLED:
        return AgentResult(
            "Antigravity",
            model or "disabled",
            "Antigravity reviewer is disabled by policy because the CLI loads user "
            "tool permission rules and has no no-tools or safe-mode switch. An "
            "administrator may opt in at MCP startup with "
            "MULTI_AGENT_ENABLE_UNCONFINED_ANTIGRAVITY_REVIEWER=1.",
            status="unavailable",
            requested_model=model,
            error_message="Antigravity reviewer is disabled by startup policy.",
        )
    _validate_cli_model(model)
    agy = _resolve_command(
        "MULTI_AGENT_ANTIGRAVITY_CMD",
        ["agy.exe", "agy"],
        AGY_BIN / "agy.exe",
    )
    _require_native_prompt_command(agy)
    full_prompt = _readonly_prompt(prompt, working_dir, context_files)
    run_marker = f"router-run-id:{uuid.uuid4().hex}"
    cli_prompt = f"[{run_marker}]\n{full_prompt}"
    if len(cli_prompt) > ANTIGRAVITY_MAX_PROMPT_CHARS:
        return AgentResult(
            "Antigravity",
            model or "unknown",
            "Antigravity review context is too large for safe direct CLI transport. "
            "Select fewer or smaller context_files.",
            status="unsafe_request",
            requested_model=model,
            error_message="Antigravity prompt exceeds the safe direct transport limit.",
        )
    command = [
        agy,
        "--print",
        cli_prompt,
        "--print-timeout",
        f"{timeout_sec}s",
        "--mode",
        "plan",
        "--sandbox",
        "--disable-slash-commands",
    ]
    if model:
        command.extend(["--model", model])
    start_time = time.time()
    review_dir = _create_review_dir()
    try:
        completed = _run_agent_process(
            command,
            str(review_dir),
            timeout_sec + 10,
            allowed_auth_env_names=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        )
        output = _process_output(completed, max_chars)
        transcript = _latest_antigravity_transcript(start_time, run_marker)
        transcript_answer: str | None = None
        actual_model: str | None = None
        if transcript:
            transcript_answer, actual_model = _extract_antigravity_details(transcript)
        if completed.returncode != 0:
            return _agent_failure(
                "Antigravity", model, completed, max_chars, actual_model
            )
        answer = transcript_answer or completed.stdout.strip() or output
        canonical_model = _canonicalize_antigravity_model(actual_model)
        return AgentResult(
            "Antigravity",
            canonical_model or actual_model or model or "unknown",
            _redact_secrets(answer[:max_chars]),
            requested_model=model,
            observed_models=(canonical_model,) if canonical_model else (),
            exit_code=completed.returncode,
        )
    finally:
        _remove_review_dir(review_dir)


def _ask_lm_studio(
    prompt: str,
    working_dir: str,
    timeout_sec: int,
    max_chars: int,
    context_files: Sequence[str] | None = None,
    model: str | None = None,
    max_tokens: int = LM_STUDIO_MAX_TOKENS,
    reasoning_effort: str | None = LM_STUDIO_REASONING_EFFORT,
) -> AgentResult:
    selected_model = (model or LM_STUDIO_DEFAULT_MODEL).strip()
    if not selected_model:
        return AgentResult(
            "LM Studio",
            "unconfigured",
            "No LM Studio model is configured. Set MULTI_AGENT_LM_STUDIO_MODEL.",
            status="unavailable",
            error_message="No LM Studio model is configured.",
        )

    advertised_models = _lm_studio_model_ids(timeout_sec=min(timeout_sec, 30))
    if selected_model not in advertised_models:
        available = ", ".join(advertised_models) or "none"
        return AgentResult(
            "LM Studio",
            f"{selected_model} requested; unavailable",
            "Requested model is not advertised by LM Studio. "
            f"Available model IDs: {available}",
            status="unavailable",
            requested_model=selected_model,
            error_message="Requested LM Studio model is not advertised.",
        )

    full_prompt = _readonly_prompt(prompt, working_dir, context_files)
    request_payload: dict[str, object] = {
        "model": selected_model,
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": max(1, max_tokens),
        "temperature": 0,
        "stream": False,
    }
    if reasoning_effort:
        request_payload["reasoning_effort"] = reasoning_effort

    response = _lm_studio_json_request(
        "POST",
        "chat/completions",
        request_payload,
        timeout_sec=timeout_sec,
    )
    answer, actual_model, finish_reason = _extract_lm_studio_chat_response(response)
    model_label = actual_model or selected_model
    if actual_model and actual_model != selected_model:
        return AgentResult(
            "LM Studio",
            actual_model,
            "Model mismatch: "
            f"requested {selected_model}, but LM Studio served {actual_model}. Response discarded.",
            status="invalid_output",
            requested_model=selected_model,
            observed_models=(actual_model,),
            error_message="LM Studio served a different model than requested.",
        )
    if not answer:
        reason = finish_reason or "missing"
        usage = response.get("usage")
        completion_details = (
            usage.get("completion_tokens_details") if isinstance(usage, dict) else None
        )
        reasoning_tokens = (
            completion_details.get("reasoning_tokens")
            if isinstance(completion_details, dict)
            else None
        )
        reasoning_note = (
            f" Reasoning tokens consumed: {reasoning_tokens}."
            if isinstance(reasoning_tokens, int)
            else ""
        )
        return AgentResult(
            "LM Studio",
            model_label,
            f"LM Studio returned no assistant text (finish_reason: {reason}).{reasoning_note}",
            status="invalid_output",
            requested_model=selected_model,
            observed_models=(actual_model,) if actual_model else (),
            error_message="LM Studio returned no assistant text.",
        )
    if finish_reason and finish_reason != "stop":
        answer = f"{answer}\n\n[LM Studio finish_reason: {finish_reason}]"
    return AgentResult(
        "LM Studio",
        model_label,
        _redact_secrets(answer[:max_chars]),
        requested_model=selected_model,
        observed_models=(actual_model,) if actual_model else (),
    )


def _safe_agent_call(name: str, model: str | None, callback) -> AgentResult:
    try:
        result = callback()
        requested_model = result.requested_model or model
        if (
            result.status == "ok"
            and _model_match(requested_model, result.observed_models, result.model)
            == "mismatch"
        ):
            observed_label = ", ".join(result.observed_models)
            return AgentResult(
                result.name,
                result.model,
                "Model mismatch: requested "
                f"{requested_model}, but the provider reported {observed_label}. "
                "Response discarded.",
                status="invalid_output",
                requested_model=requested_model,
                observed_models=result.observed_models,
                exit_code=result.exit_code,
                error_message="The provider reported a different model than requested.",
            )
        return result
    except LMStudioError as exc:
        message = _redact_secrets(f"LM Studio invocation failed: {exc}")
        return AgentResult(
            name,
            model or LM_STUDIO_DEFAULT_MODEL or "unknown",
            message,
            status="unavailable",
            requested_model=model,
            error_message=message,
        )
    except subprocess.TimeoutExpired as exc:
        message = _redact_secrets(f"CLI invocation timed out: {exc}")
        return AgentResult(
            name,
            model or "unknown",
            message,
            status="timeout",
            requested_model=model,
            error_message=message,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        message = _redact_secrets(f"CLI invocation failed: {exc}")
        return AgentResult(
            name,
            model or "unknown",
            message,
            status="unavailable",
            requested_model=model,
            error_message=message,
        )


def _command_version_text(command: str) -> str:
    try:
        completed = _run_agent_process([command, "--version"], str(SERVER_ROOT), 15)
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    text = _redact_secrets((completed.stdout or completed.stderr).strip())
    return text.splitlines()[0] if completed.returncode == 0 and text else "unavailable"


def _antigravity_model_catalog() -> dict[str, str]:
    command = _resolve_command(
        "MULTI_AGENT_ANTIGRAVITY_CMD",
        ["agy.exe", "agy"],
        AGY_BIN / "agy.exe",
    )
    completed = _run_agent_process([command, "models"], str(SERVER_ROOT), 30)
    catalog: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        fields = line.strip().split(maxsplit=1)
        if fields and _SAFE_CLI_MODEL.fullmatch(fields[0]):
            catalog[fields[0]] = fields[1].strip() if len(fields) > 1 else fields[0]
    return catalog


def _canonicalize_antigravity_model(actual_model: str | None) -> str | None:
    if not actual_model:
        return None
    if _SAFE_CLI_MODEL.fullmatch(actual_model):
        return actual_model
    try:
        catalog = _antigravity_model_catalog()
    except (OSError, subprocess.SubprocessError):
        return None
    normalized_label = actual_model.strip().casefold()
    for model_id, display_name in catalog.items():
        if display_name.casefold() == normalized_label:
            return model_id
    return None


def _available_models(agent: str) -> list[str]:
    normalized = agent.strip().lower()
    if normalized == "codex":
        command = _resolve_codex_command()
        completed = _run_agent_process(
            [command, "debug", "models"], str(SERVER_ROOT), 45
        )
        try:
            payload = json.loads(completed.stdout)
            return [
                item["slug"]
                for item in payload.get("models", [])
                if isinstance(item.get("slug"), str)
            ]
        except (json.JSONDecodeError, AttributeError, TypeError):
            return []
    if normalized == "claude":
        return []
    if normalized == "copilot":
        command = _resolve_command(
            "MULTI_AGENT_COPILOT_CMD",
            ["copilot.cmd", "copilot"],
            NPM_BIN / "copilot.cmd",
        )
        completed = _run_agent_process(
            [command, "help", "config"], str(SERVER_ROOT), 30
        )
        return list(
            dict.fromkeys(
                re.findall(r'^\s+- "([^"]+)"$', completed.stdout, re.MULTILINE)
            )
        )
    if normalized in {"antigravity", "agy"}:
        return list(_antigravity_model_catalog())
    if normalized in {"lm studio", "lm-studio", "lm_studio", "lmstudio", "local"}:
        return _lm_studio_model_ids()
    raise ValueError(f"Unknown agent: {agent}")


_STRUCTURED_AGENT_IDS = (
    "codex",
    "lmstudio",
    "claude",
    "copilot",
    "antigravity",
)
StructuredAgentId = Literal["codex", "lmstudio", "claude", "copilot", "antigravity"]
AgentPurpose = Literal["general", "implementation", "review"]
AdvisoryWritePolicy = Literal["read_only", "patch_proposal"]
_AGENT_DISPLAY_NAMES = {
    "codex": "Codex",
    "lmstudio": "LM Studio",
    "claude": "Claude",
    "copilot": "Copilot",
    "antigravity": "Antigravity",
}


def _normalize_agent_id(agent_id: str) -> str:
    normalized = (
        agent_id.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    )
    aliases = {"lmstudio": "lmstudio", "local": "lmstudio", "agy": "antigravity"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in _STRUCTURED_AGENT_IDS:
        raise ValueError(
            f"Unknown agent_id {agent_id!r}; expected one of {', '.join(_STRUCTURED_AGENT_IDS)}"
        )
    return normalized


def _build_agent_brief(
    task: str,
    purpose: str,
    acceptance_criteria: Sequence[str],
    write_policy: str,
    context_snapshot: str = "",
) -> str:
    if purpose not in {"general", "implementation", "review"}:
        raise ValueError("purpose must be general, implementation, or review")
    if write_policy not in {"read_only", "patch_proposal"}:
        raise ValueError(
            "write_policy must be read_only or patch_proposal; direct external-agent writes are disabled"
        )
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must not be empty")
    if not all(isinstance(item, str) for item in acceptance_criteria):
        raise ValueError("acceptance_criteria must contain only strings")
    policy_text = (
        "Read and analyze only."
        if write_policy == "read_only"
        else "Propose patch content only; do not edit files or change external state."
    )
    criteria = (
        "\n".join(f"- {_redact_secrets(item)}" for item in acceptance_criteria)
        or "- No additional criteria supplied."
    )
    brief = _redact_secrets(
        textwrap.dedent(
            f"""
            Purpose: {purpose}
            Task: {task.strip()}
            Required write policy: {write_policy}. {policy_text}

            Acceptance criteria:
            {criteria}

            Return concise findings, proposed changes, risks, and tests. Do not claim
            a check ran unless it actually ran. Distinguish observed facts from inference.
            """
        ).strip()
    )
    if context_snapshot:
        brief += "\n\nAuthorized context snapshot:\n" + _redact_secrets(
            context_snapshot
        )
    return brief


def _model_match(
    requested_model: str | None,
    observed_models: Sequence[str],
    primary_model: str | None = None,
) -> str:
    if not requested_model or not observed_models:
        return "unverified"
    if primary_model and primary_model in observed_models:
        return "confirmed" if requested_model == primary_model else "mismatch"
    return "confirmed" if requested_model in observed_models else "mismatch"


def _structured_agent_payload(
    agent_id: str,
    requested_model: str | None,
    result: AgentResult,
    duration_ms: int,
) -> dict:
    observed_models = list(dict.fromkeys(result.observed_models))
    model_match = _model_match(requested_model, observed_models, result.model)
    status = result.status
    result_text = _redact_secrets(result.content)
    error_message = (
        _redact_secrets(result.error_message) if result.error_message else None
    )
    if status == "ok" and model_match == "mismatch":
        requested_label = _redact_secrets(requested_model or "unknown")
        observed_label = ", ".join(_redact_secrets(item) for item in observed_models)
        status = "invalid_output"
        result_text = (
            "Model mismatch: requested "
            f"{requested_label}, but the provider reported {observed_label}. "
            "Response discarded."
        )
        error_message = "The provider reported a different model than requested."
    safe_requested_model = _redact_secrets(requested_model) if requested_model else None
    safe_observed_models = [_redact_secrets(item) for item in observed_models]
    return {
        "schemaVersion": 1,
        "agentId": agent_id,
        "displayName": _AGENT_DISPLAY_NAMES[agent_id],
        "requestedModel": safe_requested_model,
        "observedModels": safe_observed_models,
        "modelMatch": model_match,
        "status": status,
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "durationMs": max(0, duration_ms),
        "exitCode": result.exit_code,
        "resultText": result_text,
        "errorMessage": error_message,
    }


def _requested_model_for(agent_id: str, models: dict[str, str] | None) -> str | None:
    requested: str | None = None
    if models:
        for raw_agent_id, raw_model in models.items():
            if _normalize_agent_id(raw_agent_id) == agent_id:
                if not isinstance(raw_model, str) or not raw_model.strip():
                    raise ValueError("Every models value must be a non-empty string")
                requested = raw_model.strip()
                break
    if agent_id == "lmstudio" and not requested:
        requested = LM_STUDIO_DEFAULT_MODEL or None
    return requested


def _preflight_structured_request(
    agent_models: dict[str, str | None],
    working_dir: str,
    context_files: Sequence[str] | None,
) -> str:
    """Validate every input that could otherwise fail after a reviewer starts."""
    context_snapshot = _context_from_files(
        working_dir, context_files, DEFAULT_MAX_FILE_CHARS
    )
    for agent_id, requested_model in agent_models.items():
        if agent_id != "lmstudio":
            _validate_cli_model(requested_model)
    return context_snapshot


def _invoke_structured_agent(
    agent_id: str,
    brief: str,
    working_dir: str,
    context_files: Sequence[str] | None,
    requested_model: str | None,
    timeout_sec: int,
    lm_studio_max_tokens: int,
    lm_studio_reasoning_effort: str | None,
) -> dict:
    callbacks = {
        "codex": lambda: _ask_codex(
            brief,
            working_dir,
            timeout_sec,
            DEFAULT_MAX_CHARS,
            context_files,
            requested_model,
        ),
        "claude": lambda: _ask_claude(
            brief,
            working_dir,
            timeout_sec,
            DEFAULT_MAX_CHARS,
            context_files,
            requested_model,
        ),
        "copilot": lambda: _ask_copilot(
            brief,
            working_dir,
            timeout_sec,
            DEFAULT_MAX_CHARS,
            context_files,
            requested_model,
        ),
        "antigravity": lambda: _ask_antigravity(
            brief,
            working_dir,
            timeout_sec,
            DEFAULT_MAX_CHARS,
            context_files,
            requested_model,
        ),
        "lmstudio": lambda: _ask_lm_studio(
            brief,
            working_dir,
            timeout_sec,
            DEFAULT_MAX_CHARS,
            context_files,
            requested_model,
            lm_studio_max_tokens,
            lm_studio_reasoning_effort,
        ),
    }
    start = time.monotonic()
    try:
        result = _safe_agent_call(
            _AGENT_DISPLAY_NAMES[agent_id], requested_model, callbacks[agent_id]
        )
    except ValueError as exc:
        message = _redact_secrets(str(exc))
        result = AgentResult(
            _AGENT_DISPLAY_NAMES[agent_id],
            requested_model or "unknown",
            message,
            status="unsafe_request",
            requested_model=requested_model,
            error_message=message,
        )
    except (TypeError, KeyError) as exc:
        message = _redact_secrets(
            f"The reviewer returned malformed structured output ({type(exc).__name__})."
        )
        result = AgentResult(
            _AGENT_DISPLAY_NAMES[agent_id],
            requested_model or "unknown",
            message,
            status="invalid_output",
            requested_model=requested_model,
            error_message=message,
        )
    duration_ms = round((time.monotonic() - start) * 1000)
    return _structured_agent_payload(agent_id, requested_model, result, duration_ms)


def _doctor_agent_records() -> list[dict]:
    definitions = {
        "codex": _resolve_codex_command,
        "claude": lambda: _resolve_command(
            "MULTI_AGENT_CLAUDE_CMD", ["claude.cmd", "claude"], NPM_BIN / "claude.cmd"
        ),
        "copilot": lambda: _resolve_command(
            "MULTI_AGENT_COPILOT_CMD",
            ["copilot.cmd", "copilot"],
            NPM_BIN / "copilot.cmd",
        ),
        "antigravity": lambda: _resolve_command(
            "MULTI_AGENT_ANTIGRAVITY_CMD", ["agy.exe", "agy"], AGY_BIN / "agy.exe"
        ),
    }
    records: list[dict] = []
    for agent_id, resolver in definitions.items():
        gated = (agent_id == "codex" and not CODEX_REVIEWER_ENABLED) or (
            agent_id == "antigravity" and not ANTIGRAVITY_REVIEWER_ENABLED
        )
        if gated:
            records.append(
                {
                    "agentId": agent_id,
                    "status": "disabled_by_policy",
                    "version": None,
                }
            )
            continue
        try:
            command = resolver()
            version = _command_version_text(command)
            records.append(
                {
                    "agentId": agent_id,
                    "status": "available"
                    if version != "unavailable"
                    else "unavailable",
                    "version": version if version != "unavailable" else None,
                }
            )
        except (OSError, subprocess.SubprocessError):
            records.append(
                {"agentId": agent_id, "status": "unavailable", "version": None}
            )
    return records


@mcp.tool()
def doctor(timeout_sec: int = 15) -> str:
    """Return structured, non-secret availability and security-policy diagnostics."""
    if not 1 <= timeout_sec <= 60:
        raise ValueError("timeout_sec must be between 1 and 60")
    agents = _doctor_agent_records()
    lm_studio = _lm_studio_models_result(timeout_sec)
    agents.append(
        {
            "agentId": "lmstudio",
            "status": lm_studio["status"],
            "configuredModelAvailable": lm_studio["configuredModelAvailable"],
        }
    )
    available = any(item["status"] == "available" for item in agents)
    report = {
        "schemaVersion": 1,
        "status": "ok" if available else "degraded",
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "security": {
            "externalWritePolicy": "read_only_or_patch_proposal_only",
            "allowedContextRoots": len(ALLOWED_CONTEXT_ROOTS),
            "minimalChildEnvironment": True,
            "codexReviewerEnabled": CODEX_REVIEWER_ENABLED,
            "antigravityReviewerEnabled": ANTIGRAVITY_REVIEWER_ENABLED,
            "lmStudioRedirectsAllowed": False,
        },
        "agents": agents,
        "lmStudio": lm_studio,
    }
    return _redact_secrets(json.dumps(report, ensure_ascii=False, indent=2))


@mcp.tool()
def list_lmstudio_models(timeout_sec: int = 15) -> str:
    """List merged native and OpenAI-compatible LM Studio model metadata."""
    if not 1 <= timeout_sec <= 60:
        raise ValueError("timeout_sec must be between 1 and 60")
    return _redact_secrets(
        json.dumps(_lm_studio_models_result(timeout_sec), ensure_ascii=False, indent=2)
    )


@mcp.tool()
def run_agent(
    agent_id: StructuredAgentId,
    task: str,
    working_dir: str | None = None,
    context_files: list[str] | None = None,
    purpose: AgentPurpose = "general",
    acceptance_criteria: list[str] | None = None,
    models: dict[str, str] | None = None,
    write_policy: AdvisoryWritePolicy = "read_only",
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    lm_studio_max_tokens: int = LM_STUDIO_MAX_TOKENS,
    lm_studio_reasoning_effort: str | None = LM_STUDIO_REASONING_EFFORT,
) -> str:
    """Run one policy-confined external adviser and return structured evidence."""
    canonical_id = _normalize_agent_id(agent_id)
    requested_model = _requested_model_for(canonical_id, models)
    if write_policy not in {"read_only", "patch_proposal"}:
        unsafe = AgentResult(
            _AGENT_DISPLAY_NAMES[canonical_id],
            requested_model or "unknown",
            "Direct external-agent writes are disabled.",
            status="unsafe_request",
            requested_model=requested_model,
            error_message="write_policy must be read_only or patch_proposal.",
        )
        return json.dumps(
            _structured_agent_payload(canonical_id, requested_model, unsafe, 0),
            ensure_ascii=False,
            indent=2,
        )
    if not 1 <= timeout_sec <= 3600:
        raise ValueError("timeout_sec must be between 1 and 3600")
    if lm_studio_max_tokens < 1:
        raise ValueError("lm_studio_max_tokens must be positive")
    cwd = _normalize_working_dir(working_dir)
    context_snapshot = _preflight_structured_request(
        {canonical_id: requested_model}, cwd, context_files
    )
    brief = _build_agent_brief(
        task,
        purpose,
        acceptance_criteria or (),
        write_policy,
        context_snapshot,
    )
    payload = _invoke_structured_agent(
        canonical_id,
        brief,
        cwd,
        None,
        requested_model,
        timeout_sec,
        lm_studio_max_tokens,
        lm_studio_reasoning_effort,
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def run_panel(
    task: str,
    agent_ids: list[StructuredAgentId] | None = None,
    working_dir: str | None = None,
    context_files: list[str] | None = None,
    purpose: AgentPurpose = "general",
    acceptance_criteria: list[str] | None = None,
    models: dict[str, str] | None = None,
    write_policy: AdvisoryWritePolicy = "read_only",
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    lm_studio_max_tokens: int = LM_STUDIO_MAX_TOKENS,
    lm_studio_reasoning_effort: str | None = LM_STUDIO_REASONING_EFFORT,
) -> str:
    """Run independent external advisers concurrently; defaults to Claude and Copilot."""
    selected = agent_ids if agent_ids is not None else ["claude", "copilot"]
    canonical_ids = list(dict.fromkeys(_normalize_agent_id(item) for item in selected))
    if not canonical_ids:
        return json.dumps(
            {
                "schemaVersion": 1,
                "status": "unavailable",
                "durationMs": 0,
                "results": [],
            },
            indent=2,
        )
    if write_policy not in {"read_only", "patch_proposal"}:
        results = []
        for agent_id in canonical_ids:
            requested_model = _requested_model_for(agent_id, models)
            unsafe = AgentResult(
                _AGENT_DISPLAY_NAMES[agent_id],
                requested_model or "unknown",
                "Direct external-agent writes are disabled.",
                status="unsafe_request",
                requested_model=requested_model,
                error_message="write_policy must be read_only or patch_proposal.",
            )
            results.append(
                _structured_agent_payload(agent_id, requested_model, unsafe, 0)
            )
        return json.dumps(
            {
                "schemaVersion": 1,
                "status": "unsafe_request",
                "durationMs": 0,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    if not 1 <= timeout_sec <= 3600:
        raise ValueError("timeout_sec must be between 1 and 3600")
    if lm_studio_max_tokens < 1:
        raise ValueError("lm_studio_max_tokens must be positive")
    cwd = _normalize_working_dir(working_dir)
    requested_models = {
        agent_id: _requested_model_for(agent_id, models) for agent_id in canonical_ids
    }
    context_snapshot = _preflight_structured_request(
        requested_models, cwd, context_files
    )
    brief = _build_agent_brief(
        task,
        purpose,
        acceptance_criteria or (),
        write_policy,
        context_snapshot,
    )
    panel_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(canonical_ids)) as executor:
        futures = [
            executor.submit(
                _invoke_structured_agent,
                agent_id,
                brief,
                cwd,
                None,
                requested_models[agent_id],
                timeout_sec,
                lm_studio_max_tokens,
                lm_studio_reasoning_effort,
            )
            for agent_id in canonical_ids
        ]
        results = [future.result() for future in futures]
    duration_ms = round((time.monotonic() - panel_start) * 1000)
    ok_count = sum(result["status"] == "ok" for result in results)
    if ok_count == len(results):
        status = "ok"
    elif ok_count:
        status = "partial"
    elif all(result["status"] == "unsafe_request" for result in results):
        status = "unsafe_request"
    elif any(result["status"] == "invalid_output" for result in results):
        status = "invalid_output"
    else:
        status = "unavailable"
    return json.dumps(
        {
            "schemaVersion": 1,
            "status": status,
            "durationMs": max(0, duration_ms),
            "results": results,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def get_agent_status() -> str:
    """Report local agent availability, interface, model visibility, and override support."""
    definitions = [
        ("Codex", _resolve_codex_command),
        (
            "Claude",
            lambda: _resolve_command(
                "MULTI_AGENT_CLAUDE_CMD",
                ["claude.cmd", "claude"],
                NPM_BIN / "claude.cmd",
            ),
        ),
        (
            "Copilot",
            lambda: _resolve_command(
                "MULTI_AGENT_COPILOT_CMD",
                ["copilot.cmd", "copilot"],
                NPM_BIN / "copilot.cmd",
            ),
        ),
        (
            "Antigravity",
            lambda: _resolve_command(
                "MULTI_AGENT_ANTIGRAVITY_CMD", ["agy.exe", "agy"], AGY_BIN / "agy.exe"
            ),
        ),
    ]
    rows = [
        "| Agent | Available | Interface/version | Default/actual model | `model` override |",
        "|---|---|---|---|---|",
    ]
    for name, resolver in definitions:
        if name == "Codex" and not CODEX_REVIEWER_ENABLED:
            rows.append(
                "| Codex | disabled by policy | not started | "
                "read-only sandbox does not confine reads | no |"
            )
            continue
        if name == "Antigravity" and not ANTIGRAVITY_REVIEWER_ENABLED:
            rows.append(
                "| Antigravity | disabled by policy | not started | "
                "user tool permission rules are not isolated | no |"
            )
            continue
        try:
            command = resolver()
            version = _command_version_text(command).replace("|", "\\|")
            default_model = _codex_default_model(command) if name == "Codex" else None
            model_text = default_model or "reported by the CLI on invocation"
            rows.append(f"| {name} | yes | {version} | {model_text} | yes |")
        except (OSError, subprocess.SubprocessError):
            rows.append(f"| {name} | no | unavailable | unavailable | no |")
    try:
        models = _lm_studio_model_ids(timeout_sec=min(DEFAULT_TIMEOUT_SEC, 15))
        model_state = (
            "advertised"
            if LM_STUDIO_DEFAULT_MODEL and LM_STUDIO_DEFAULT_MODEL in models
            else "not advertised"
        )
        configured_model = LM_STUDIO_DEFAULT_MODEL or "not configured"
        rows.append(
            "| LM Studio | yes | "
            f"OpenAI-compatible API ({LM_STUDIO_BASE_URL}) | "
            f"{configured_model} ({model_state}) | yes |"
        )
    except LMStudioError:
        rows.append(
            "| LM Studio | no | "
            f"OpenAI-compatible API ({LM_STUDIO_BASE_URL}) | unavailable | no |"
        )
    return _redact_secrets("\n".join(rows))


@mcp.tool()
def list_agent_models(agent: str = "all") -> str:
    """List model names exposed by the selected agent; use agent='all' for every service."""
    requested = (
        ["codex", "claude", "copilot", "antigravity", "lmstudio"]
        if agent.lower() == "all"
        else [agent]
    )
    sections: list[str] = []
    for name in requested:
        try:
            models = _available_models(name)
            if name.strip().lower() == "claude" and not models:
                detail = (
                    "- Claude CLI does not expose a model list. Use a full model ID "
                    "for a confirmable override; aliases cannot be matched exactly to "
                    "runtime evidence and may return invalid_output."
                )
            else:
                detail = (
                    "\n".join(f"- {model}" for model in models)
                    or "- CLI did not expose a model list"
                )
        except (OSError, subprocess.SubprocessError, ValueError, LMStudioError) as exc:
            detail = f"- unavailable: {exc}"
        display_name = (
            "LM Studio"
            if name.strip().lower()
            in {"lmstudio", "lm-studio", "lm_studio", "lm studio"}
            else name.title()
        )
        sections.append(f"## {display_name}\n\n{detail}")
    return _redact_secrets("\n\n".join(sections))


@mcp.tool()
def ask_codex(
    prompt: str,
    working_dir: str | None = None,
    context_files: list[str] | None = None,
    model: str | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> str:
    """Ask Codex only after an administrator opts into its unconfined file-read risk."""
    cwd = _normalize_working_dir(working_dir)
    result = _safe_agent_call(
        "Codex",
        model,
        lambda: _ask_codex(
            prompt, cwd, timeout_sec, DEFAULT_MAX_CHARS, context_files, model
        ),
    )
    return result.render()


@mcp.tool()
def ask_claude(
    prompt: str,
    working_dir: str | None = None,
    context_files: list[str] | None = None,
    model: str | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> str:
    """Ask tool-disabled Claude Code for an advisory second opinion."""
    cwd = _normalize_working_dir(working_dir)
    result = _safe_agent_call(
        "Claude",
        model,
        lambda: _ask_claude(
            prompt, cwd, timeout_sec, DEFAULT_MAX_CHARS, context_files, model
        ),
    )
    return result.render()


@mcp.tool()
def ask_copilot(
    prompt: str,
    working_dir: str | None = None,
    context_files: list[str] | None = None,
    model: str | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> str:
    """Ask view-confined GitHub Copilot CLI for an advisory second opinion."""
    cwd = _normalize_working_dir(working_dir)
    result = _safe_agent_call(
        "Copilot",
        model,
        lambda: _ask_copilot(
            prompt, cwd, timeout_sec, DEFAULT_MAX_CHARS, context_files, model
        ),
    )
    return result.render()


@mcp.tool()
def ask_antigravity(
    prompt: str,
    working_dir: str | None = None,
    context_files: list[str] | None = None,
    model: str | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> str:
    """Ask Antigravity only after an administrator opts into its user-rule risk."""
    cwd = _normalize_working_dir(working_dir)
    result = _safe_agent_call(
        "Antigravity",
        model,
        lambda: _ask_antigravity(
            prompt, cwd, timeout_sec, DEFAULT_MAX_CHARS, context_files, model
        ),
    )
    return result.render()


@mcp.tool()
def ask_lm_studio(
    prompt: str,
    working_dir: str | None = None,
    context_files: list[str] | None = None,
    model: str | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    max_tokens: int = LM_STUDIO_MAX_TOKENS,
    reasoning_effort: str | None = LM_STUDIO_REASONING_EFFORT,
) -> str:
    """Ask the configured local LM Studio model for a read-only second opinion."""
    cwd = _normalize_working_dir(working_dir)
    requested_model = model or LM_STUDIO_DEFAULT_MODEL
    result = _safe_agent_call(
        "LM Studio",
        requested_model,
        lambda: _ask_lm_studio(
            prompt,
            cwd,
            timeout_sec,
            DEFAULT_MAX_CHARS,
            context_files,
            model,
            max_tokens,
            reasoning_effort,
        ),
    )
    return result.render()


@mcp.tool()
def collect_reviews(
    prompt: str,
    working_dir: str | None = None,
    context_files: list[str] | None = None,
    include_codex: bool = False,
    include_claude: bool = True,
    include_copilot: bool = True,
    include_antigravity: bool = False,
    include_lm_studio: bool = False,
    codex_model: str | None = None,
    claude_model: str | None = None,
    copilot_model: str | None = None,
    antigravity_model: str | None = None,
    lm_studio_model: str | None = None,
    lm_studio_max_tokens: int = LM_STUDIO_MAX_TOKENS,
    lm_studio_reasoning_effort: str | None = LM_STUDIO_REASONING_EFFORT,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> str:
    """Collect parallel advisory reviews; Codex remains startup-policy gated."""
    cwd = _normalize_working_dir(working_dir)
    if not 1 <= timeout_sec <= 3600:
        raise ValueError("timeout_sec must be between 1 and 3600")
    if lm_studio_max_tokens < 1:
        raise ValueError("lm_studio_max_tokens must be positive")
    selected_cli_models = (
        (include_codex, codex_model),
        (include_claude, claude_model),
        (include_copilot, copilot_model),
        (include_antigravity, antigravity_model),
    )
    for included, selected_model in selected_cli_models:
        if included:
            _validate_cli_model(selected_model)
    context_snapshot = _context_from_files(cwd, context_files, DEFAULT_MAX_FILE_CHARS)
    review_prompt = prompt
    if context_snapshot:
        review_prompt += "\n\nAuthorized context snapshot:\n" + context_snapshot

    jobs: list[tuple[str, str | None, object]] = []
    if include_codex:
        jobs.append(
            (
                "Codex",
                codex_model,
                lambda: _ask_codex(
                    review_prompt,
                    cwd,
                    timeout_sec,
                    DEFAULT_MAX_CHARS,
                    None,
                    codex_model,
                ),
            )
        )
    if include_claude:
        jobs.append(
            (
                "Claude",
                claude_model,
                lambda: _ask_claude(
                    review_prompt,
                    cwd,
                    timeout_sec,
                    DEFAULT_MAX_CHARS,
                    None,
                    claude_model,
                ),
            )
        )
    if include_copilot:
        jobs.append(
            (
                "Copilot",
                copilot_model,
                lambda: _ask_copilot(
                    review_prompt,
                    cwd,
                    timeout_sec,
                    DEFAULT_MAX_CHARS,
                    None,
                    copilot_model,
                ),
            )
        )
    if include_antigravity:
        jobs.append(
            (
                "Antigravity",
                antigravity_model,
                lambda: _ask_antigravity(
                    review_prompt,
                    cwd,
                    timeout_sec,
                    DEFAULT_MAX_CHARS,
                    None,
                    antigravity_model,
                ),
            )
        )
    if include_lm_studio:
        requested_lm_studio_model = lm_studio_model or LM_STUDIO_DEFAULT_MODEL
        jobs.append(
            (
                "LM Studio",
                requested_lm_studio_model,
                lambda: _ask_lm_studio(
                    review_prompt,
                    cwd,
                    timeout_sec,
                    DEFAULT_MAX_CHARS,
                    None,
                    lm_studio_model,
                    lm_studio_max_tokens,
                    lm_studio_reasoning_effort,
                ),
            )
        )
    if not jobs:
        return "No agents were selected."

    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = [
            executor.submit(_safe_agent_call, name, model, callback)
            for name, model, callback in jobs
        ]
        results = [future.result() for future in futures]
    return "\n\n---\n\n".join(result.render() for result in results)


if __name__ == "__main__":
    mcp.run()
