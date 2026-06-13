"""Central configuration. Everything is overridable via environment / .env so
the same code runs headless in CI and headed for a screen-recorded demo."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional
    pass

from orchestrator.trace import DEFAULT_PRICING

ROOT = Path(__file__).resolve().parent


def _b(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    # --- browser ---
    headless: bool = field(default_factory=lambda: _b("HEADLESS", True))
    slow_mo_ms: int = field(default_factory=lambda: _i("SLOW_MO", 0))
    nav_timeout_ms: int = field(default_factory=lambda: _i("NAV_TIMEOUT", 45000))
    action_timeout_ms: int = field(default_factory=lambda: _i("ACTION_TIMEOUT", 15000))
    user_agent: str = field(
        default_factory=lambda: os.environ.get(
            "USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
    )

    # --- task (Hugging Face text-generation models by likes) ---
    target_url: str = field(
        default_factory=lambda: os.environ.get("TARGET_URL", "https://huggingface.co/models")
    )
    base_url: str = "https://huggingface.co"
    task_filter: str = field(default_factory=lambda: os.environ.get("TASK_FILTER", "text-generation"))
    task_filter_label: str = field(
        default_factory=lambda: os.environ.get("TASK_FILTER_LABEL", "Text Generation")
    )
    sort_by: str = field(default_factory=lambda: os.environ.get("SORT_BY", "likes"))
    sort_label: str = field(default_factory=lambda: os.environ.get("SORT_LABEL", "Most likes"))
    top_n: int = field(default_factory=lambda: _i("TOP_N", 3))

    # --- llm gateway ---
    api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.environ.get("LLM_MODEL", "claude-sonnet-4-6"))
    vision_model: str = field(
        default_factory=lambda: os.environ.get("VISION_MODEL", os.environ.get("LLM_MODEL", "claude-sonnet-4-6"))
    )
    max_tokens: int = field(default_factory=lambda: _i("LLM_MAX_TOKENS", 1500))

    # --- demo behaviour ---
    # Run an explicit (clearly-labelled) vision set-of-marks read on one model
    # page so the report can showcase the vision path even when the cheaper
    # paths already succeeded. Auto-disabled when no API key is present.
    force_vision_demo: bool = field(default_factory=lambda: _b("FORCE_VISION_DEMO", True))

    # When set (and no real key), use the offline DEMO gateway (mocked LLM) so a
    # single command populates the LLM plan / vision read / cost for a recording.
    demo_mode: bool = field(default_factory=lambda: _b("DEMO_MODE", False))

    pricing: Dict[str, tuple] = field(default_factory=lambda: dict(DEFAULT_PRICING))

    @property
    def llm_enabled(self) -> bool:
        return bool(self.api_key)
