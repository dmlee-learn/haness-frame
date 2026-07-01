from __future__ import annotations

import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.error
import urllib.parse
import urllib.request

from .db import (
    DEFAULT_ROLE_OPTIONS,
    delete_ai_service,
    get_ai_service,
    get_setting,
    list_ai_services,
    load_project_settings,
    project_role_assignments,
    read_project_working_description,
    save_project_settings,
    set_setting,
    upsert_ai_service,
)
from .i18n import SUPPORTED_LANGUAGES, normalize_language, parse_cookies, tr
from .paths import DB, project_dir, project_file_rows, project_zip_bytes, safe_project_path, write_project_file
from .project_docs import (
    build_agent_routing,
    build_project_settings_doc,
    build_workspace_services_json,
    create_project_files,
)


def nav_html(lang: str) -> str:
    return (
        f'<nav><a href="/">{html.escape(tr(lang, "nav.create_project"))}</a> | '
        f'<a href="/projects">{html.escape(tr(lang, "nav.projects"))}</a> | '
        f'<a href="/settings">{html.escape(tr(lang, "nav.ai_services"))}</a> | '
        f'<a href="/preferences">{html.escape(tr(lang, "nav.preferences"))}</a></nav>'
    )


def provider_options(selected: str) -> str:
    providers = [
        "openai_compatible",
        "vllm",
        "ollama",
        "codex",
        "anthropic",
        "openai",
        "gemini",
        "other",
    ]
    return "".join(
        f'<option value="{provider}"{" selected" if provider == selected else ""}>{provider}</option>'
        for provider in providers
    )


def language_options(selected: str) -> str:
    return "".join(
        f'<option value="{code}"{" selected" if code == selected else ""}>{html.escape(label)}</option>'
        for code, label in SUPPORTED_LANGUAGES.items()
    )


def service_options(selected: str, services: list) -> str:
    options = ['<option value="">--</option>']
    for service in services:
        name = service["name"]
        company = service["company"] or ""
        model = service["model"] or ""
        label = name
        if company or model:
            label = f"{name} ({company}/{model})".strip(" /")
        options.append(
            f'<option value="{html.escape(name)}"{" selected" if name == selected else ""}>{html.escape(label)}</option>'
        )
    return "".join(options)


def project_form_html(message: str = "", lang: str = "en") -> str:
    escaped_message = html.escape(message)
    return f"""<!doctype html>
<html lang="{html.escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>haness-frame project creator</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 880px; margin: 32px auto; padding: 0 20px; line-height: 1.5; }}
    label {{ display: block; font-weight: 600; margin-top: 18px; }}
    input, textarea {{ width: 100%; box-sizing: border-box; font: inherit; padding: 10px; margin-top: 6px; }}
    textarea {{ min-height: 120px; }}
    button {{ margin-top: 20px; padding: 10px 16px; font: inherit; }}
    .message {{ white-space: pre-wrap; background: #f3f5f7; padding: 12px; margin: 16px 0; }}
    .hint {{ color: #444; font-size: 0.95rem; }}
  </style>
</head>
<body>
  {nav_html(lang)}
  <h1>{html.escape(tr(lang, "project.title"))}</h1>
  <p class="hint">{html.escape(tr(lang, "project.hint"))} <code>context/original-request.md</code>.</p>
  {"<div class='message'>" + escaped_message + "</div>" if message else ""}
  <form method="post" accept-charset="utf-8">
    <label for="project">{html.escape(tr(lang, "project.folder_name"))}</label>
    <input id="project" name="project" placeholder="internal-business-system" required>

    <label for="english_description">{html.escape(tr(lang, "project.english_description"))}</label>
    <textarea id="english_description" name="english_description" required placeholder="Build an internal business system for approvals, task requests, document management, messaging, leave requests, and organization management"></textarea>

    <label for="original_request">{html.escape(tr(lang, "project.original_request"))}</label>
    <textarea id="original_request" name="original_request" placeholder="Original request in any language"></textarea>

    <label>
      <input type="checkbox" name="force" value="1" style="width:auto">
      {html.escape(tr(lang, "project.overwrite"))}
    </label>

    <button type="submit">{html.escape(tr(lang, "project.create_button"))}</button>
  </form>
</body>
</html>
"""


def projects_html(message: str = "", lang: str = "en") -> str:
    rows = []
    from .paths import list_projects

    for project in list_projects():
        name = html.escape(project["name"])
        description = html.escape(project["description"])
        updated = html.escape(project["updated"])
        url_name = urllib.parse.quote(project["name"])
        rows.append(
            "<tr>"
            f"<td><a href='/project?name={url_name}'>{name}</a></td>"
            f"<td>{description}</td>"
            f"<td>{updated}</td>"
            f"<td><a href='/download?name={url_name}'>Download ZIP</a></td>"
            "</tr>"
        )
    escaped_message = html.escape(message)
    body_rows = "".join(rows) if rows else "<tr><td colspan='4'>No projects yet.</td></tr>"
    return f"""<!doctype html>
<html lang="{html.escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>haness-frame projects</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 1180px; margin: 32px auto; padding: 0 20px; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 18px; }}
    th, td {{ border: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f5f7; }}
    .message {{ white-space: pre-wrap; background: #f3f5f7; padding: 12px; margin: 16px 0; }}
  </style>
</head>
<body>
  {nav_html(lang)}
  <h1>{html.escape(tr(lang, "projects.title"))}</h1>
  {"<div class='message'>" + escaped_message + "</div>" if message else ""}
  <table>
    <thead>
      <tr><th>{html.escape(tr(lang, "common.name"))}</th><th>{html.escape(tr(lang, "projects.working_description"))}</th><th>{html.escape(tr(lang, "projects.updated"))}</th><th>{html.escape(tr(lang, "projects.download"))}</th></tr>
    </thead>
    <tbody>{body_rows}</tbody>
  </table>
</body>
</html>
"""


def project_detail_html(name: str, message: str = "", lang: str = "en") -> str:
    path = safe_project_path(name)
    if path is None:
        return projects_html(f"Project not found: {name}", lang)
    settings = load_project_settings(name)
    assignments = settings.get("role_assignments", {})
    services = list_ai_services()

    file_rows = []
    for file_info in project_file_rows(path):
        file_rows.append(
            "<tr>"
            f"<td>{html.escape(file_info['path'])}</td>"
            f"<td>{html.escape(file_info['size'])}</td>"
            "</tr>"
        )
    routing_rows = []
    for role in DEFAULT_ROLE_OPTIONS:
        selected = str(assignments.get(role, ""))
        routing_rows.append(
            "<tr>"
            f"<td>{html.escape(role)}</td>"
            f"<td><select name='role_{html.escape(role)}'>{service_options(selected, services)}</select></td>"
            "</tr>"
        )

    escaped_name = html.escape(name)
    escaped_message = html.escape(message)
    url_name = urllib.parse.quote(name)
    body_rows = "".join(file_rows) if file_rows else "<tr><td colspan='2'>No files.</td></tr>"
    routing_rows_html = "".join(routing_rows)
    return f"""<!doctype html>
<html lang="{html.escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_name}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 1180px; margin: 32px auto; padding: 0 20px; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 18px; }}
    th, td {{ border: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f5f7; }}
    .message {{ white-space: pre-wrap; background: #f3f5f7; padding: 12px; margin: 16px 0; }}
    .section {{ margin-top: 28px; }}
  </style>
</head>
<body>
  {nav_html(lang)}
  <h1>{escaped_name}</h1>
  {"<div class='message'>" + escaped_message + "</div>" if message else ""}
  <p><a href="/download?name={url_name}">{html.escape(tr(lang, "projects.download_zip"))}</a></p>
  <p><code>{html.escape(str(path))}</code></p>

  <div class="section">
    <h2>{html.escape(tr(lang, "project.role_routing"))}</h2>
    <form method="post" action="/project?name={url_name}" accept-charset="utf-8">
      <input type="hidden" name="action" value="save_routing">
      <table>
        <thead>
          <tr><th>{html.escape(tr(lang, "settings.roles"))}</th><th>{html.escape(tr(lang, "project.service"))}</th></tr>
        </thead>
        <tbody>{routing_rows_html}</tbody>
      </table>
      <button type="submit">{html.escape(tr(lang, "project.save_routing"))}</button>
    </form>
  </div>

  <div class="section">
    <h2>{html.escape(tr(lang, "project.files"))}</h2>
    <table>
      <thead>
        <tr><th>{html.escape(tr(lang, "project_detail.file"))}</th><th>{html.escape(tr(lang, "project_detail.size"))}</th></tr>
      </thead>
      <tbody>{body_rows}</tbody>
    </table>
  </div>
</body>
</html>
"""


def preferences_html(message: str = "", lang: str = "en") -> str:
    default_lang = normalize_language(get_setting("default_ui_language", "en"))
    escaped_message = html.escape(message)
    return f"""<!doctype html>
<html lang="{html.escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(tr(lang, "preferences.title"))}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 880px; margin: 32px auto; padding: 0 20px; line-height: 1.5; }}
    label {{ display: block; font-weight: 600; margin-top: 18px; }}
    select {{ width: 100%; box-sizing: border-box; font: inherit; padding: 8px; margin-top: 4px; }}
    button {{ margin-top: 18px; padding: 10px 16px; font: inherit; }}
    .message {{ white-space: pre-wrap; background: #f3f5f7; padding: 12px; margin: 16px 0; }}
  </style>
</head>
<body>
  {nav_html(lang)}
  <h1>{html.escape(tr(lang, "preferences.title"))}</h1>
  {"<div class='message'>" + escaped_message + "</div>" if message else ""}
  <form method="post" action="/preferences" accept-charset="utf-8">
    <label for="user_language">{html.escape(tr(lang, "preferences.user_language"))}</label>
    <select id="user_language" name="user_language">{language_options(lang)}</select>
    <button type="submit" name="action" value="save_user_language">{html.escape(tr(lang, "preferences.save_user_language"))}</button>
  </form>
  <form method="post" action="/preferences" accept-charset="utf-8">
    <label for="default_language">{html.escape(tr(lang, "preferences.default_language"))}</label>
    <select id="default_language" name="default_language">{language_options(default_lang)}</select>
    <button type="submit" name="action" value="save_default_language">{html.escape(tr(lang, "preferences.save_default_language"))}</button>
  </form>
</body>
</html>
"""


def settings_html(message: str = "", lang: str = "en", edit_name: str = "") -> str:
    services = list_ai_services()
    edit_service = get_ai_service(edit_name) if edit_name else None
    edit_roles = set((edit_service["roles"] if edit_service else "").split(","))
    rows = []
    for service in services:
        url_name = urllib.parse.quote(service["name"])
        rows.append(
            "<tr>"
            f"<td>{html.escape(service['name'])}</td>"
            f"<td>{html.escape(service['company'])}</td>"
            f"<td>{html.escape(service['provider_type'])}</td>"
            f"<td>{html.escape(service['roles'])}</td>"
            f"<td>{html.escape(service['model'])}</td>"
            f"<td>{html.escape(service['base_url'])}</td>"
            f"<td>{'yes' if service['enabled'] else 'no'}</td>"
            f"<td>{html.escape(service['api_key_env'])}</td>"
            f"<td>{html.escape(service['notes'])}</td>"
            f"<td><a href='/settings?edit={url_name}'>{html.escape(tr(lang, 'common.edit'))}</a> "
            f"<form method='post' action='/settings' style='display:inline'>"
            f"<input type='hidden' name='action' value='delete'>"
            f"<input type='hidden' name='name' value='{html.escape(service['name'])}'>"
            f"<button type='submit'>{html.escape(tr(lang, 'common.delete'))}</button></form></td>"
            "</tr>"
        )
    escaped_message = html.escape(message)
    role_boxes = []
    for role in DEFAULT_ROLE_OPTIONS:
        checked = " checked" if role in edit_roles else ""
        role_boxes.append(
            f"<label style='font-weight:400'><input type='checkbox' name='roles' value='{role}' style='width:auto'{checked}> {role}</label>"
        )
    form_value = lambda key: html.escape(edit_service[key]) if edit_service else ""
    enabled_checked = " checked" if edit_service and edit_service["enabled"] else ""
    return f"""<!doctype html>
<html lang="{html.escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>haness-frame AI services</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 1180px; margin: 32px auto; padding: 0 20px; line-height: 1.5; }}
    label {{ display: block; font-weight: 600; margin-top: 14px; }}
    input, textarea, select {{ width: 100%; box-sizing: border-box; font: inherit; padding: 8px; margin-top: 4px; }}
    textarea {{ min-height: 70px; }}
    button {{ margin-top: 18px; padding: 10px 16px; font: inherit; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 18px; font-size: 0.92rem; }}
    th, td {{ border: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f5f7; }}
    .message {{ white-space: pre-wrap; background: #f3f5f7; padding: 12px; margin: 16px 0; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  </style>
</head>
<body>
  {nav_html(lang)}
  <h1>{html.escape(tr(lang, "settings.title"))}</h1>
  <p>{html.escape(tr(lang, "settings.db_hint"))} <code>{html.escape(str(DB))}</code>. {html.escape(tr(lang, "settings.key_hint"))}</p>
  {"<div class='message'>" + escaped_message + "</div>" if message else ""}

  <h2>{html.escape(tr(lang, "settings.configured_services"))}</h2>
  <table>
    <thead>
      <tr>
        <th>{html.escape(tr(lang, "common.name"))}</th><th>{html.escape(tr(lang, "settings.company"))}</th><th>{html.escape(tr(lang, "settings.provider"))}</th><th>{html.escape(tr(lang, "settings.roles"))}</th><th>{html.escape(tr(lang, "settings.model"))}</th><th>{html.escape(tr(lang, "settings.base_url"))}</th><th>{html.escape(tr(lang, "settings.enabled"))}</th><th>{html.escape(tr(lang, "settings.api_key_env"))}</th><th>{html.escape(tr(lang, "settings.notes"))}</th><th>{html.escape(tr(lang, "common.actions"))}</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>

  <h2>{html.escape(tr(lang, "settings.edit_service"))}</h2>
  <form method="post" action="/settings" accept-charset="utf-8">
    <input type="hidden" name="action" value="save">
    <div class="grid">
      <div>
        <label for="name">{html.escape(tr(lang, "common.name"))}</label>
        <input id="name" name="name" placeholder="local-vllm" value="{form_value('name')}" required>
      </div>
      <div>
        <label for="company">{html.escape(tr(lang, "settings.company"))}</label>
        <input id="company" name="company" placeholder="openai, anthropic, local" value="{form_value('company')}">
      </div>
      <div>
        <label for="provider_type">{html.escape(tr(lang, "settings.provider"))}</label>
        <select id="provider_type" name="provider_type">
          {provider_options(form_value('provider_type'))}
        </select>
      </div>
      <div>
        <label>{html.escape(tr(lang, "settings.roles"))}</label>
        {''.join(role_boxes)}
      </div>
      <div>
        <label for="model">{html.escape(tr(lang, "settings.model"))}</label>
        <input id="model" name="model" placeholder="Qwen/Qwen3-8B-AWQ" value="{form_value('model')}">
      </div>
      <div>
        <label for="base_url">{html.escape(tr(lang, "settings.base_url"))}</label>
        <input id="base_url" name="base_url" placeholder="http://127.0.0.1:8000/v1" value="{form_value('base_url')}">
      </div>
      <div>
        <label for="api_key_env">{html.escape(tr(lang, "settings.api_key_env"))}</label>
        <input id="api_key_env" name="api_key_env" placeholder="ANTHROPIC_API_KEY" value="{form_value('api_key_env')}">
      </div>
    </div>
    <label>
      <input type="checkbox" name="enabled" value="1" style="width:auto"{enabled_checked}>
      {html.escape(tr(lang, "settings.enabled"))}
    </label>
    <label for="notes">{html.escape(tr(lang, "settings.notes"))}</label>
    <textarea id="notes" name="notes">{form_value('notes')}</textarea>
    <button type="submit">{html.escape(tr(lang, "settings.save_service"))}</button>
  </form>
</body>
</html>
"""


class ProjectServer(BaseHTTPRequestHandler):
    def current_language(self) -> str:
        cookies = parse_cookies(self.headers.get("Cookie", ""))
        raw_cookie_lang = cookies.get("haness_lang", "")
        if raw_cookie_lang in SUPPORTED_LANGUAGES:
            return raw_cookie_lang
        return normalize_language(get_setting("default_ui_language", "en"))

    def send_html(self, body: str, status: int = 200, headers: dict[str, str] | None = None) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def send_bytes(self, payload: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        lang = self.current_language()
        if parsed.path == "/settings":
            edit_name = query.get("edit", [""])[0]
            self.send_html(settings_html(lang=lang, edit_name=edit_name))
            return
        if parsed.path == "/preferences":
            self.send_html(preferences_html(lang=lang))
            return
        if parsed.path == "/projects":
            self.send_html(projects_html(lang=lang))
            return
        if parsed.path == "/project":
            name = query.get("name", [""])[0]
            self.send_html(project_detail_html(name, lang=lang))
            return
        if parsed.path == "/download":
            name = query.get("name", [""])[0]
            path = safe_project_path(name)
            if path is None:
                self.send_html(projects_html(f"Project not found: {name}", lang), 404)
                return
            payload = project_zip_bytes(path)
            self.send_bytes(payload, "application/zip", f"{path.name}.zip")
            return
        if parsed.path != "/":
            self.send_html(project_form_html("Use / to create a project.", lang), 404)
            return
        self.send_html(project_form_html(lang=lang))

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        lang = self.current_language()
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        form = urllib.parse.parse_qs(raw_body, keep_blank_values=True)

        if parsed.path == "/settings":
            action = form.get("action", ["save"])[0]
            if action == "delete":
                name = form.get("name", [""])[0].strip()
                if name:
                    delete_ai_service(name)
                self.send_html(settings_html(f"Deleted service: {name}", lang))
                return
            data = {key: values[0] for key, values in form.items()}
            data["roles"] = ",".join(form.get("roles", []))
            if not data.get("name") or not data.get("provider_type"):
                self.send_html(settings_html("Name and provider type are required.", lang), 400)
                return
            upsert_ai_service(data)
            self.send_html(settings_html(f"Saved service: {data.get('name', '').strip()}", lang))
            return

        if parsed.path == "/preferences":
            action = form.get("action", [""])[0]
            if action == "save_default_language":
                selected = normalize_language(form.get("default_language", ["en"])[0])
                set_setting("default_ui_language", selected)
                self.send_html(preferences_html("Default language saved.", selected))
                return
            selected = normalize_language(form.get("user_language", ["en"])[0])
            headers = {"Set-Cookie": f"haness_lang={urllib.parse.quote(selected)}; Path=/; SameSite=Lax"}
            self.send_html(preferences_html("User language saved in cookie.", selected), headers=headers)
            return

        if parsed.path == "/project":
            project_name = query.get("name", [""])[0]
            if not project_name:
                self.send_html(projects_html("Project name is required.", lang), 400)
                return
            action = form.get("action", [""])[0]
            if action != "save_routing":
                self.send_html(project_detail_html(project_name, "Unsupported project action.", lang), 400)
                return
            role_assignments: dict[str, str] = {}
            for role in DEFAULT_ROLE_OPTIONS:
                selected_service = form.get(f"role_{role}", [""])[0].strip()
                if selected_service:
                    role_assignments[role] = selected_service
            save_project_settings(project_name, role_assignments)
            working_description = read_project_working_description(project_name)
            if working_description:
                routing_doc = build_agent_routing(working_description, role_assignments)
                settings_doc = build_project_settings_doc(project_name, working_description, role_assignments)
                base = project_dir(project_name, project_name)
                write_project_file(base / "docs" / "04-agent-routing.md", routing_doc, True)
                write_project_file(base / "docs" / "05-project-settings.md", settings_doc, True)
                write_project_file(
                    base / "workspace" / "services.json",
                    build_workspace_services_json(project_name, role_assignments),
                    True,
                )
            self.send_html(project_detail_html(project_name, "Saved role routing.", lang))
            return

        if parsed.path != "/":
            self.send_html(project_form_html("Use / to create a project.", lang), 404)
            return

        project = form.get("project", [""])[0].strip()
        english_description = form.get("english_description", [""])[0].strip()
        original_request = form.get("original_request", [""])[0].strip() or english_description
        force = form.get("force", [""])[0] == "1"

        if not project or not english_description:
            self.send_html(project_form_html("Project and English working description are required.", lang), 400)
            return

        base, created, skipped = create_project_files(
            project=project,
            original_request=original_request,
            english_description=english_description,
            force=force,
        )
        message = f"Project harness created.\n\nPath: {base}\nCreated: {created}\nSkipped: {skipped}"
        message += f"\n\nManage: /project?name={base.name}\nDownload: /download?name={base.name}"
        if skipped:
            message += "\n\nEnable overwrite if you want to replace existing generated files."
        self.send_html(project_form_html(message, lang))


def cmd_serve(args) -> int:
    from .db import init_db

    init_db()
    server = HTTPServer((args.host, args.port), ProjectServer)
    url = f"http://{args.host}:{args.port}/"
    print(f"haness-frame project creator: {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0
