"""
Search Providers
─────────────────
Unified interface for all search backends.
Switch via pipeline.json: search.provider = "google" | "bing" | "serpapi" | "searx"
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    position: int = 0


class BaseSearchProvider(ABC):
    @abstractmethod
    async def search(
        self, session: aiohttp.ClientSession, query: str, max_results: int
    ) -> list[SearchResult]:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...


# ── Google Custom Search ──────────────────────────────────────────────────────

class GoogleSearchProvider(BaseSearchProvider):
    BASE_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self):
        self.api_key = os.environ["GOOGLE_SEARCH_API_KEY"]
        self.cx = os.environ["GOOGLE_SEARCH_CX"]

    @property
    def provider_name(self) -> str:
        return "google"

    async def search(
        self, session: aiohttp.ClientSession, query: str, max_results: int
    ) -> list[SearchResult]:
        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "num": min(max_results, 10),
        }
        async with session.get(self.BASE_URL, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()

        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                position=i,
            )
            for i, item in enumerate(data.get("items", []))
        ]


# ── Bing Web Search ───────────────────────────────────────────────────────────

class BingSearchProvider(BaseSearchProvider):
    BASE_URL = "https://api.bing.microsoft.com/v7.0/search"

    def __init__(self):
        self.api_key = os.environ["BING_SEARCH_API_KEY"]

    @property
    def provider_name(self) -> str:
        return "bing"

    async def search(
        self, session: aiohttp.ClientSession, query: str, max_results: int
    ) -> list[SearchResult]:
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        params = {"q": query, "count": min(max_results, 50), "mkt": "en-US"}
        async with session.get(self.BASE_URL, params=params, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()

        return [
            SearchResult(
                title=item.get("name", ""),
                url=item.get("url", ""),
                snippet=item.get("snippet", ""),
                position=i,
            )
            for i, item in enumerate(
                data.get("webPages", {}).get("value", [])
            )
        ]


# ── SerpAPI (Google wrapper, paid) ────────────────────────────────────────────

class SerpAPIProvider(BaseSearchProvider):
    BASE_URL = "https://serpapi.com/search"

    def __init__(self):
        self.api_key = os.environ["SERPAPI_KEY"]

    @property
    def provider_name(self) -> str:
        return "serpapi"

    async def search(
        self, session: aiohttp.ClientSession, query: str, max_results: int
    ) -> list[SearchResult]:
        params = {
            "q": query,
            "api_key": self.api_key,
            "engine": "google",
            "num": min(max_results, 10),
        }
        async with session.get(self.BASE_URL, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()

        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                position=i,
            )
            for i, item in enumerate(data.get("organic_results", []))
        ]


# ── Searx (self-hosted, free) ─────────────────────────────────────────────────

class SearxProvider(BaseSearchProvider):
    def __init__(self):
        self.base_url = os.getenv("SEARX_BASE_URL", "http://localhost:8080")

    @property
    def provider_name(self) -> str:
        return "searx"

    async def search(
        self, session: aiohttp.ClientSession, query: str, max_results: int
    ) -> list[SearchResult]:
        params = {"q": query, "format": "json", "categories": "general"}
        async with session.get(f"{self.base_url}/search", params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()

        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                position=i,
            )
            for i, item in enumerate(data.get("results", [])[:max_results])
        ]


# ── Registry ──────────────────────────────────────────────────────────────────

_SEARCH_PROVIDERS: dict[str, type[BaseSearchProvider]] = {
    "google":  GoogleSearchProvider,
    "bing":    BingSearchProvider,
    "serpapi": SerpAPIProvider,
    "searx":   SearxProvider,
}


def get_search_provider(name: str) -> BaseSearchProvider:
    cls = _SEARCH_PROVIDERS.get(name.lower())
    if not cls:
        raise ValueError(
            f"Unknown search provider '{name}'. "
            f"Available: {list(_SEARCH_PROVIDERS)}"
        )
    return cls()
