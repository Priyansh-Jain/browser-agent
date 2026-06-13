"""Orchestrator-level control-flow exceptions."""
from __future__ import annotations


class GatewayBlocked(Exception):
    """Raised by the Browser skill when a site blocks automation (captcha,
    bot-wall, 403/429, login required) and recovery failed. The orchestrator
    records it as a ``blocked`` step and lets the run finish so the report can
    still be produced."""


class SkillError(Exception):
    """A skill failed in an unrecoverable way."""
