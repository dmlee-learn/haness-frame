from __future__ import annotations

import json
import urllib.parse
import webbrowser

from .audit import log_event
from .evidence import write_evidence_draft, write_evidence_gaps
from .scorecard import mark_check
from .storage import read_text, write_text

SEARCH_PLAN_JSON = "workspace/evidence/search-plan.json"


def suggested_queries() -> list[str]:
    backlog = read_text("research/search-backlog.md", "")
    in_block = False
    queries: list[str] = []
    for line in backlog.splitlines():
        stripped = line.strip()
        if stripped == "```text":
            in_block = True
            continue
        if in_block and stripped == "```":
            break
        if in_block and stripped:
            queries.append(stripped)
    return queries


def build_search_plan(provider: str = "google") -> dict[str, object]:
    queries = suggested_queries()
    searches = []
    for query in queries:
        encoded = urllib.parse.quote_plus(query)
        if provider == "github":
            url = f"https://github.com/search?q={encoded}&type=repositories"
        else:
            url = f"https://www.google.com/search?q={encoded}"
        searches.append({"query": query, "provider": provider, "url": url})
    plan = {"provider": provider, "searches": searches}
    write_text(SEARCH_PLAN_JSON, json.dumps(plan, indent=2, ensure_ascii=False))
    write_evidence_draft()
    write_evidence_gaps()
    mark_check("search_plan", True, f"{len(searches)} search(es)")
    log_event("search.plan.created", provider=provider, count=len(searches))
    return plan


def open_search(index: int = 1, provider: str = "google") -> dict[str, object]:
    plan = build_search_plan(provider)
    searches = plan.get("searches", [])
    if not isinstance(searches, list) or not searches:
        raise ValueError("no search queries found in research/search-backlog.md")
    if index < 1 or index > len(searches):
        raise ValueError(f"search index out of range: {index}")
    search = searches[index - 1]
    url = str(search["url"])
    webbrowser.open(url)
    log_event("search.opened", index=index, url=url)
    return search
