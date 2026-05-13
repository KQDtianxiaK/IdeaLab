from __future__ import annotations

import os
from typing import Any

import requests

from .config import load_local_env


class SemanticScholarTool:
    name = "semantic_scholar"

    def search(self, query: str, limit: int = 6) -> dict[str, Any]:
        query = " ".join(str(query).split())[:220]
        load_local_env()
        headers = {}
        api_key = os.getenv("S2_API_KEY")
        if not api_key:
            return {
                "ok": False,
                "query": query,
                "error": "Missing S2_API_KEY; skipped network literature search.",
                "papers": [],
            }
        if api_key:
            headers["X-API-KEY"] = api_key
        try:
            response = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                headers=headers,
                params={
                    "query": query,
                    "limit": limit,
                    "fields": "title,authors,venue,year,abstract,citationCount,url",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            papers = data.get("data", [])
            papers.sort(key=lambda p: p.get("citationCount") or 0, reverse=True)
            return {"ok": True, "query": query, "papers": papers[:limit]}
        except Exception as exc:
            return {"ok": False, "query": query, "error": str(exc), "papers": []}
