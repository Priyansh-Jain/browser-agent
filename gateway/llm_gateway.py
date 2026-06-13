"""llm_gateway -- the single choke-point for every model call.

Why a gateway? So that (a) token usage + cost are metered in one place and fed
straight into the Trace, (b) the provider is swappable, and (c) the entire agent
degrades gracefully to a deterministic, LLM-free mode when no API key is present
(every method simply returns ``None`` and callers fall back to rules).
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from anthropic import Anthropic  # type: ignore

    _SDK_OK = True
except Exception:  # pragma: no cover
    Anthropic = None  # type: ignore
    _SDK_OK = False


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _extract_json(text: str) -> Optional[Any]:
    if not text:
        return None
    cleaned = _FENCE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        # find first {...} or [...] block
        for opener, closer in (("{", "}"), ("[", "]")):
            i, j = cleaned.find(opener), cleaned.rfind(closer)
            if 0 <= i < j:
                try:
                    return json.loads(cleaned[i : j + 1])
                except Exception:
                    continue
    return None


class LLMGateway:
    def __init__(self, config: Any, trace: Any = None) -> None:
        self.config = config
        self.trace = trace
        self.model = config.llm_model
        self.vision_model = config.vision_model
        self._client = None
        self.reason_unavailable = ""
        if not config.api_key:
            self.reason_unavailable = "ANTHROPIC_API_KEY not set"
        elif not _SDK_OK:
            self.reason_unavailable = "anthropic SDK not importable"
        else:
            try:
                self._client = Anthropic(api_key=config.api_key)
            except Exception as e:  # pragma: no cover
                self.reason_unavailable = f"client init failed: {e}"

    @property
    def available(self) -> bool:
        return self._client is not None

    # ---- core call ----
    def _call(
        self,
        user_content: Any,
        system: str = "",
        purpose: str = "",
        max_tokens: Optional[int] = None,
        temperature: float = 0.0,
        model: Optional[str] = None,
    ) -> Optional[str]:
        if not self.available:
            return None
        try:
            resp = self._client.messages.create(
                model=model or self.model,
                max_tokens=max_tokens or self.config.max_tokens,
                temperature=temperature,
                system=system or "You are a precise data-extraction and planning assistant.",
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception as e:
            if self.trace:
                self.trace.log(f"LLM call failed ({purpose}): {e!r}", "warn")
            return None
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        if self.trace and getattr(resp, "usage", None):
            self.trace.record_llm(
                model or self.model,
                resp.usage.input_tokens,
                resp.usage.output_tokens,
                purpose,
            )
        return text

    def complete(self, prompt: str, system: str = "", purpose: str = "", **kw: Any) -> Optional[str]:
        return self._call(prompt, system=system, purpose=purpose, **kw)

    def json(
        self, prompt: str, system: str = "", purpose: str = "", retries: int = 1, **kw: Any
    ) -> Optional[Any]:
        """Ask for strict JSON and parse it. Returns None if unavailable/unparseable."""
        sys = (system + "\n\n" if system else "") + "Respond with ONLY valid JSON. No prose, no code fences."
        text = self._call(prompt, system=sys, purpose=purpose, **kw)
        data = _extract_json(text or "")
        attempt = 0
        while data is None and text and attempt < retries:
            attempt += 1
            text = self._call(
                prompt + "\n\nYour previous reply was not valid JSON. Return ONLY a JSON value.",
                system=sys,
                purpose=purpose + ":retry",
                **kw,
            )
            data = _extract_json(text or "")
        return data

    def vision(
        self,
        prompt: str,
        image_path: str,
        system: str = "",
        purpose: str = "vision",
        media_type: str = "image/png",
        **kw: Any,
    ) -> Optional[str]:
        if not self.available:
            return None
        try:
            b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        except Exception as e:  # pragma: no cover
            if self.trace:
                self.trace.log(f"vision image read failed: {e!r}", "warn")
            return None
        content: List[Dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
            {"type": "text", "text": prompt},
        ]
        return self._call(content, system=system, purpose=purpose, model=self.vision_model, **kw)
