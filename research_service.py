"""
Research Service (v2 — config-driven)
Uses cfg.llm for query generation and fact extraction.
Uses cfg.search for web search.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path

import aiohttp

from ..config.loader import RuntimeConfig
from ..utils.models import ResearchFinding, ResearchResult

logger = logging.getLogger(__name__)


class ResearchService:
    def __init__(self, cfg: RuntimeConfig):
        self.cfg = cfg
        self.cache_dir = Path(cfg.cache_dir) / "research"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def research(self, topic: str) -> ResearchResult:
        logger.info(f"[Research] Topic: {topic}")
        queries = await self._generate_queries(topic)

        all_findings: list[ResearchFinding] = []
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"},
        ) as session:
            results = await asyncio.gather(
                *[self._search_cached(session, q) for q in queries],
                return_exceptions=True,
            )
            for r in results:
                if not isinstance(r, Exception):
                    all_findings.extend(r)

            seen: set[str] = set()
            unique = [f for f in all_findings if not (f.url in seen or seen.add(f.url))]
            top_n = self.cfg._raw["search"]["top_pages_to_fetch"]
            top = sorted(unique, key=lambda x: x.relevance_score, reverse=True)[:top_n]
            await asyncio.gather(*[self._fetch_content(session, f) for f in top], return_exceptions=True)

        return await self._extract_facts(topic, unique)

    async def _generate_queries(self, topic: str) -> list[str]:
        resp = await self.cfg.llm.complete(
            user_prompt=(
                f"Generate 4 targeted search queries to research this topic for a YouTube "
                f"tech video: '{topic}'\n\nReturn ONLY a JSON array of strings."
            ),
            max_tokens=512,
        )
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.text.strip())
        try:
            queries = json.loads(raw)
            return queries[:4] if isinstance(queries, list) else [topic]
        except json.JSONDecodeError:
            return [topic, f"{topic} announcement", f"{topic} review"]

    async def _search_cached(self, session, query: str) -> list[ResearchFinding]:
        cache_key = hashlib.md5(f"{self.cfg.search.provider_name}:{query}".encode()).hexdigest()
        cache_path = self.cache_dir / f"search_{cache_key}.json"
        if cache_path.exists():
            return [ResearchFinding(**f) for f in json.loads(cache_path.read_text())]
        raw_results = await self.cfg.search.search(session, query, self.cfg._raw["search"]["max_results"])
        findings = [
            ResearchFinding(title=r.title, url=r.url, snippet=r.snippet, relevance_score=1.0 - r.position * 0.1)
            for r in raw_results
        ]
        cache_path.write_text(json.dumps([f.__dict__ for f in findings], default=str))
        return findings

    async def _fetch_content(self, session, finding: ResearchFinding) -> None:
        cache_key = hashlib.md5(finding.url.encode()).hexdigest()
        cache_path = self.cache_dir / f"page_{cache_key}.txt"
        if cache_path.exists():
            finding.full_content = cache_path.read_text()
            return
        try:
            async with session.get(finding.url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return
                html = await resp.text(errors="replace")
            text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL)
            text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()[:8000]
            finding.full_content = text
            cache_path.write_text(text)
        except Exception as exc:
            logger.warning(f"[Research] Fetch failed {finding.url}: {exc}")

    async def _extract_facts(self, topic: str, findings: list[ResearchFinding]) -> ResearchResult:
        snippets = "\n\n".join(
            f"SOURCE: {f.title}\nURL: {f.url}\n{(f.full_content or f.snippet)[:1500]}\n---"
            for f in findings[:8]
        )
        resp = await self.cfg.llm.complete(
            user_prompt=(
                f"Researching '{topic}' for a YouTube tech video.\n\nSources:\n{snippets}\n\n"
                'Return JSON: { "key_facts": [...], "structured_summary": "...", "query_used": "..." }\n'
                "8-15 specific key_facts. Return ONLY valid JSON."
            ),
            max_tokens=2048,
        )
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.text.strip())
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"key_facts": [f.snippet for f in findings[:8]], "structured_summary": f"Research on: {topic}", "query_used": topic}
        return ResearchResult(
            topic=topic, query_used=data.get("query_used", topic), findings=findings,
            key_facts=data.get("key_facts", []), structured_summary=data.get("structured_summary", ""),
            relevant_urls=[f.url for f in findings if f.full_content],
        )
