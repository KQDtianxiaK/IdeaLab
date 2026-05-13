from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from .config import get_models_config, load_local_env


def extract_json(text: str) -> Any:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([i for i in [text.find("{"), text.find("[")] if i >= 0], default=-1)
        if start >= 0:
            candidate = text[start:]
            for end in range(len(candidate), 0, -1):
                try:
                    return json.loads(candidate[:end])
                except json.JSONDecodeError:
                    continue
        raise


class LLMClient:
    def __init__(self) -> None:
        self.config = get_models_config()

    def stage_config(self, stage: str) -> dict[str, Any]:
        stage_models = self.config.get("stage_models", {})
        return stage_models.get(stage) or stage_models.get("default", {})

    def model_label(self, stage: str) -> str:
        cfg = self.stage_config(stage)
        return f"{cfg.get('provider', 'mock')}:{cfg.get('model', 'mock')}"

    def complete_json(
        self,
        stage: str,
        system: str,
        user: str,
        fallback: Any,
    ) -> tuple[Any, dict[str, Any]]:
        load_local_env()
        cfg = self.stage_config(stage)
        provider_name = cfg.get("provider")
        provider = self.config.get("providers", {}).get(provider_name, {})
        api_key_env = provider.get("api_key_env")
        api_key = os.getenv(api_key_env or "")

        meta = {
            "provider": provider_name or "mock",
            "model": cfg.get("model") or provider.get("default_model") or "mock",
            "used_fallback": False,
        }
        if not api_key:
            meta["used_fallback"] = True
            meta["reason"] = f"Missing API key env {api_key_env}"
            return fallback, meta

        base_url = str(provider.get("base_url", "")).rstrip("/")
        url = f"{base_url}/v1/chat/completions"
        payload = {
            "model": meta["model"],
            "temperature": cfg.get("temperature", 0.4),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user + "\n\n只输出合法 JSON，不要输出 Markdown 解释。"},
            ],
        }
        max_tokens = cfg.get("max_tokens", 2000)
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=int(provider.get("timeout_seconds", 60)),
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return extract_json(content), meta
        except Exception as exc:
            meta["used_fallback"] = True
            meta["reason"] = str(exc)
            return fallback, meta
