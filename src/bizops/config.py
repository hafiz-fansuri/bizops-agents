from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Settings:
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct"))
    supervisor_model: str | None = field(default_factory=lambda: os.getenv("OLLAMA_SUPERVISOR_MODEL"))
    profile_path: str = field(default_factory=lambda: os.getenv("BIZOPS_PROFILE", "profiles/generic.yaml"))
    db_path: str = field(default_factory=lambda: os.getenv("BIZOPS_DB", "data/business.db"))
    checkpoint_db: str = field(default_factory=lambda: os.getenv("BIZOPS_CHECKPOINT_DB", "data/checkpoints.db"))


def load_profile(path: str | Path) -> dict:
    p = yaml.safe_load(Path(path).read_text())
    for req in ("business", "agents"):
        if req not in p:
            raise ValueError(f"profile {path} missing '{req}'")
    p.setdefault("supervisor", {})
    p["supervisor"].setdefault("max_steps", 6)
    p["supervisor"].setdefault("default_agent", next(iter(p["agents"])))
    p.setdefault("approval_required", [])
    p.setdefault("mcp_servers", {})
    p.setdefault("automations", [])
    return p
