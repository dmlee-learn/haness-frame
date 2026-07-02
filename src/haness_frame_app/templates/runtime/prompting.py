from __future__ import annotations

from .engine import role_packet


def build_messages(role: str, prompt: str, system: str = "") -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    packet = role_packet(role).strip()
    system_parts = [part for part in [packet, system.strip()] if part]
    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})
    messages.append({"role": "user", "content": prompt})
    return messages
