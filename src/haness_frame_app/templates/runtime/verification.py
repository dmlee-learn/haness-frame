from __future__ import annotations

import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
from .audit import log_event
from .engine import enforce_decision_gate
from .scorecard import mark_check
from .storage import ROOT, read_text, write_text

POLICY_FILE = "workspace/verification-policy.json"
LATEST_RESULT = "workspace/verifications/latest.json"
_UNSAFE_SHELL_TEXT = re.compile(r"[;&|<>`\r\n\x00]|\$\(")
_PYTHON_COMMAND = re.compile(r"^python(?:\d+(?:\.\d+)?)?(?:\.exe)?$", re.IGNORECASE)
_PY_LAUNCHER = re.compile(r"^py(?:\.exe)?$", re.IGNORECASE)
_PY_VERSION_SELECTOR = re.compile(r"^-\d+(?:\.\d+)?$")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _section_text(text: str, heading: str) -> str:
    marker = f"## {heading}"
    parts = text.split(marker, 1)
    if len(parts) != 2:
        return ""
    tail = parts[1]
    next_heading = tail.find("\n## ")
    return (tail if next_heading == -1 else tail[:next_heading]).strip()


def decision_verification_commands() -> list[str]:
    section = _section_text(read_text("docs/03-decision-record.md", ""), "Verification Commands")
    commands: list[str] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if line.startswith(("- ", "* ")):
            line = line[2:].strip()
        elif re.match(r"^\d+[.)]\s+", line):
            line = re.sub(r"^\d+[.)]\s+", "", line).strip()
        else:
            continue
        if len(line) >= 2 and line[0] == line[-1] == "`":
            line = line[1:-1].strip()
        if line:
            commands.append(line)
    return commands


def load_verification_policy() -> dict[str, object]:
    payload = read_text(POLICY_FILE, "{}")
    try:
        policy = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid verification policy JSON: {exc}") from exc
    if not isinstance(policy, dict):
        raise ValueError("verification policy must be a JSON object")
    allowed = policy.get("allowed_commands", [])
    if not isinstance(allowed, list) or not all(isinstance(item, str) and item.strip() for item in allowed):
        raise ValueError("verification policy allowed_commands must be a list of non-empty strings")
    return policy


def _split_command(command: str) -> list[str]:
    args = shlex.split(command, posix=os.name != "nt")
    if os.name == "nt":
        args = [item[1:-1] if len(item) >= 2 and item[0] == item[-1] == '"' else item for item in args]
    return args


def _command_identity(command: str) -> tuple[str, ...]:
    return tuple(_split_command(command))


def verification_plan() -> dict[str, object]:
    commands = decision_verification_commands()
    policy = load_verification_policy()
    try:
        allowed = {_command_identity(str(item)) for item in policy.get("allowed_commands", [])}
    except ValueError as exc:
        raise ValueError(f"verification policy contains invalid command syntax: {exc}") from exc
    entries = []
    for command in commands:
        unsafe = bool(_UNSAFE_SHELL_TEXT.search(command))
        try:
            identity = _command_identity(command)
            parse_error = ""
        except ValueError as exc:
            identity = ()
            parse_error = str(exc)
        approved = bool(identity in allowed and identity and not unsafe and not parse_error)
        reason = "approved"
        if unsafe:
            reason = "shell operators are not allowed"
        elif parse_error:
            reason = f"invalid command syntax: {parse_error}"
        elif identity not in allowed:
            reason = "command is not in workspace/verification-policy.json"
        entries.append({"command": command, "approved": approved, "reason": reason})
    return {
        "policy_file": POLICY_FILE,
        "commands": entries,
        "approved": bool(entries) and all(item["approved"] for item in entries),
    }


def _command_args(command: str) -> list[str]:
    if _UNSAFE_SHELL_TEXT.search(command):
        raise ValueError(f"unsafe verification command: {command}")
    args = _split_command(command)
    if not args:
        raise ValueError("verification command is empty")
    executable = args[0]
    if _PY_LAUNCHER.fullmatch(executable):
        args[0] = sys.executable
        if len(args) > 1 and _PY_VERSION_SELECTOR.fullmatch(args[1]):
            del args[1]
    elif _PYTHON_COMMAND.fullmatch(executable):
        args[0] = sys.executable
    return args


def _trim_output(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[-limit:], True


def _policy_int(policy: dict[str, object], name: str, default: int, minimum: int, maximum: int) -> int:
    value = policy.get(name, default)
    if isinstance(value, bool):
        raise ValueError(f"verification policy {name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"verification policy {name} must be an integer") from exc
    return max(minimum, min(parsed, maximum))


def run_verification_commands(*, stop_on_failure: bool = True) -> dict[str, object]:
    enforce_decision_gate("reviewer")
    plan = verification_plan()
    if not plan["commands"]:
        raise ValueError("no verification commands found in the decision record")
    rejected = [item for item in plan["commands"] if not item["approved"]]
    if rejected:
        names = ", ".join(str(item["command"]) for item in rejected)
        raise ValueError(f"verification policy rejected command(s): {names}")

    policy = load_verification_policy()
    timeout = _policy_int(policy, "timeout_seconds", 120, 1, 1800)
    output_limit = _policy_int(policy, "max_output_chars", 12000, 1000, 100000)
    started_at = _now()
    results: list[dict[str, object]] = []
    log_event("verification.started", commands=len(plan["commands"]), timeout_seconds=timeout)
    for entry in plan["commands"]:
        command = str(entry["command"])
        command_started_at = _now()
        try:
            completed = subprocess.run(
                _command_args(command),
                cwd=ROOT,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            stdout, stdout_truncated = _trim_output(completed.stdout, output_limit)
            stderr, stderr_truncated = _trim_output(completed.stderr, output_limit)
            result = {
                "command": command,
                "started_at": command_started_at,
                "completed_at": _now(),
                "returncode": completed.returncode,
                "passed": completed.returncode == 0,
                "stdout": stdout,
                "stderr": stderr,
                "output_truncated": stdout_truncated or stderr_truncated,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            stdout, _ = _trim_output(str(exc.stdout or ""), output_limit)
            stderr, _ = _trim_output(str(exc.stderr or ""), output_limit)
            result = {
                "command": command,
                "started_at": command_started_at,
                "completed_at": _now(),
                "returncode": None,
                "passed": False,
                "stdout": stdout,
                "stderr": stderr,
                "output_truncated": False,
                "timed_out": True,
            }
        except OSError as exc:
            result = {
                "command": command,
                "started_at": command_started_at,
                "completed_at": _now(),
                "returncode": None,
                "passed": False,
                "stdout": "",
                "stderr": str(exc),
                "output_truncated": False,
                "timed_out": False,
            }
        results.append(result)
        log_event(
            "verification.command.completed",
            command=command,
            passed=result["passed"],
            returncode=result["returncode"],
            timed_out=result["timed_out"],
        )
        if stop_on_failure and not result["passed"]:
            break

    passed = len(results) == len(plan["commands"]) and all(item["passed"] for item in results)
    report = {
        "started_at": started_at,
        "completed_at": _now(),
        "passed": passed,
        "stop_on_failure": stop_on_failure,
        "planned_commands": len(plan["commands"]),
        "executed_commands": len(results),
        "results": results,
    }
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    write_text(f"workspace/verifications/{stamp}.json", json.dumps(report, indent=2, ensure_ascii=False))
    write_text(LATEST_RESULT, json.dumps(report, indent=2, ensure_ascii=False))
    mark_check("verification_commands", passed, f"{len(results)}/{len(plan['commands'])} command(s) passed")
    log_event("verification.completed", passed=passed, executed=len(results), planned=len(plan["commands"]))
    return report
