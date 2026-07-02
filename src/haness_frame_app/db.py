from __future__ import annotations

import datetime as dt
import json
import pathlib
import sqlite3

from .paths import DATA, DB, project_dir

DEFAULT_ROLE_OPTIONS = [
    "project_scout",
    "context_curator",
    "researcher",
    "planner",
    "designer",
    "architect",
    "critic",
    "debugger",
    "decision_maker",
    "coder",
    "reviewer",
    "escalation",
]

DEFAULT_AI_SERVICES = [
    {
        "name": "local-vllm",
        "company": "local",
        "provider_type": "openai_compatible",
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "Qwen/Qwen3-8B-AWQ",
        "role": "fallback",
        "roles": "fallback",
        "enabled": 1,
        "notes": "Local vLLM OpenAI-compatible endpoint.",
    },
    {
        "name": "local-vllm-coder",
        "company": "local",
        "provider_type": "openai_compatible",
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "Qwen/Qwen2.5-Coder-14B-Instruct-AWQ",
        "role": "coder",
        "roles": "coder",
        "enabled": 0,
        "notes": "Local coder model profile.",
    },
    {
        "name": "ollama",
        "company": "local",
        "provider_type": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen3.5:35b",
        "role": "planner",
        "roles": "planner,reviewer",
        "enabled": 0,
        "notes": "Local Ollama planner or reviewer endpoint.",
    },
    {
        "name": "codex",
        "company": "openai",
        "provider_type": "codex",
        "base_url": "",
        "model": "codex",
        "role": "escalation",
        "roles": "escalation,coder,reviewer",
        "enabled": 0,
        "notes": "Codex or cloud coding assistant escalation path.",
    },
    {
        "name": "claude",
        "company": "anthropic",
        "provider_type": "anthropic",
        "base_url": "https://api.anthropic.com",
        "model": "claude-sonnet",
        "role": "escalation",
        "roles": "escalation,planner,reviewer",
        "enabled": 0,
        "notes": "Claude API configuration placeholder.",
    },
]


def db_connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                company TEXT NOT NULL DEFAULT '',
                provider_type TEXT NOT NULL,
                base_url TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT '',
                roles TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 0,
                api_key_env TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ensure_column(conn, "ai_services", "company", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "ai_services", "roles", "TEXT NOT NULL DEFAULT ''")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for service in DEFAULT_AI_SERVICES:
            conn.execute(
                """
                INSERT OR IGNORE INTO ai_services
                    (name, company, provider_type, base_url, model, role, roles, enabled, notes)
                VALUES
                    (:name, :company, :provider_type, :base_url, :model, :role, :roles, :enabled, :notes)
                """,
                service,
            )
            conn.execute(
                "UPDATE ai_services SET company = ? WHERE name = ? AND company = ''",
                (service["company"], service["name"]),
            )
        conn.execute("UPDATE ai_services SET roles = role WHERE roles = ''")
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('default_project_language', 'en')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('default_ui_language', 'en')"
        )


def get_setting(key: str, default: str = "") -> str:
    init_db()
    with db_connect() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    init_db()
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )


def list_ai_services() -> list[sqlite3.Row]:
    init_db()
    with db_connect() as conn:
        return list(conn.execute("SELECT * FROM ai_services ORDER BY roles, name"))


def get_ai_service(name: str) -> sqlite3.Row | None:
    init_db()
    with db_connect() as conn:
        return conn.execute("SELECT * FROM ai_services WHERE name = ?", (name,)).fetchone()


def upsert_ai_service(data: dict[str, str]) -> None:
    init_db()
    enabled = 1 if data.get("enabled") == "1" else 0
    roles = ",".join(
        role.strip()
        for role in data.get("roles", data.get("role", "")).split(",")
        if role.strip()
    )
    role = roles.split(",", 1)[0] if roles else data.get("role", "").strip()
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO ai_services
                (name, company, provider_type, base_url, model, role, roles, enabled, api_key_env, notes)
            VALUES
                (:name, :company, :provider_type, :base_url, :model, :role, :roles, :enabled, :api_key_env, :notes)
            ON CONFLICT(name) DO UPDATE SET
                company = excluded.company,
                provider_type = excluded.provider_type,
                base_url = excluded.base_url,
                model = excluded.model,
                role = excluded.role,
                roles = excluded.roles,
                enabled = excluded.enabled,
                api_key_env = excluded.api_key_env,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            {
                "name": data.get("name", "").strip(),
                "company": data.get("company", "").strip(),
                "provider_type": data.get("provider_type", "").strip(),
                "base_url": data.get("base_url", "").strip(),
                "model": data.get("model", "").strip(),
                "role": role,
                "roles": roles,
                "enabled": enabled,
                "api_key_env": data.get("api_key_env", "").strip(),
                "notes": data.get("notes", "").strip(),
            },
        )


def delete_ai_service(name: str) -> bool:
    init_db()
    with db_connect() as conn:
        result = conn.execute("DELETE FROM ai_services WHERE name = ?", (name,))
        return result.rowcount > 0


def roles_for_service(service: sqlite3.Row) -> list[str]:
    raw = service["roles"] or service["role"] or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def choose_service_for_role(role: str, services: list[sqlite3.Row]) -> sqlite3.Row | None:
    enabled_exact = [service for service in services if service["enabled"] and role in roles_for_service(service)]
    if enabled_exact:
        return enabled_exact[0]
    enabled_fallback = [service for service in services if service["enabled"] and "fallback" in roles_for_service(service)]
    if enabled_fallback:
        return enabled_fallback[0]
    enabled_services = [service for service in services if service["enabled"]]
    if enabled_services:
        return enabled_services[0]
    exact_matches = [service for service in services if role in roles_for_service(service)]
    if exact_matches:
        return exact_matches[0]
    return services[0] if services else None


def project_role_assignments() -> dict[str, str]:
    services = list_ai_services()
    assignments: dict[str, str] = {}
    for role in DEFAULT_ROLE_OPTIONS:
        service = choose_service_for_role(role, services)
        if service:
            assignments[role] = service["name"]
    return assignments


def default_project_settings() -> dict[str, object]:
    return {"role_assignments": project_role_assignments()}


def project_settings_path(project: str) -> pathlib.Path:
    return project_dir(project, project) / "project-settings.json"


def load_project_settings(project: str) -> dict[str, object]:
    path = project_settings_path(project)
    if not path.exists():
        return default_project_settings()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_project_settings()
    assignments = payload.get("role_assignments", {})
    if not isinstance(assignments, dict):
        assignments = {}
    merged = default_project_settings()["role_assignments"]
    merged.update({str(key): str(value) for key, value in assignments.items() if value})
    return {"role_assignments": merged}


def save_project_settings(project: str, role_assignments: dict[str, str]) -> None:
    path = project_settings_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "role_assignments": role_assignments,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_project_working_description(project: str) -> str:
    readme = project_dir(project, project) / "README.md"
    if not readme.exists():
        return ""
    text = readme.read_text(encoding="utf-8", errors="replace")
    marker = "## Working Description"
    if marker not in text:
        return ""
    tail = text.split(marker, 1)[1]
    return tail.split("##", 1)[0].strip()


def service_choices() -> list[str]:
    return [service["name"] for service in list_ai_services()]


def service_snapshot(service: sqlite3.Row | None) -> dict[str, object]:
    if service is None:
        return {}
    return {
        "name": service["name"],
        "company": service["company"],
        "provider_type": service["provider_type"],
        "base_url": service["base_url"],
        "model": service["model"],
        "api_key_env": service["api_key_env"],
        "enabled": bool(service["enabled"]),
        "roles": roles_for_service(service),
        "notes": service["notes"],
    }


def project_service_snapshot(role_assignments: dict[str, str]) -> dict[str, object]:
    services = {service["name"]: service for service in list_ai_services()}
    resolved: dict[str, object] = {}
    for role, service_name in role_assignments.items():
        resolved[role] = service_snapshot(services.get(service_name))
    fallback = next((service for service in services.values() if service["enabled"]), None)
    return {
        "role_services": resolved,
        "fallback_service": service_snapshot(fallback),
    }
