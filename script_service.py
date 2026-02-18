"""
Script Generation Service (v2 — config-driven)
Persona, tone and section structure all come from pipeline.json.
"""
from __future__ import annotations

import json
import logging
import re

from ..config.loader import RuntimeConfig
from ..utils.models import ResearchResult, ScriptSection, VideoScript, VisualMarker

logger = logging.getLogger(__name__)

_SYSTEM = """You are an expert YouTube scriptwriter specialising in tech content.
Write in a {tone} style for {audience}.
{style}. {opener_hook}.
Embed visual cues using [SCREENSHOT: https://url] and [VISUAL: description] markers.
Target word count: {target_words} words (~{target_minutes} minutes at 150 wpm).
Return ONLY valid JSON, no markdown fences."""

_USER = """Create a YouTube script about: {topic}

RESEARCH SUMMARY:
{summary}

KEY FACTS:
{facts}

RELEVANT URLS TO SCREENSHOT:
{urls}

Return JSON:
{{
  "title": "engaging video title",
  "sections": [
    {{
      "section_id": "intro",
      "section_type": "intro",
      "title": "Section Title",
      "narration_text": "Full narration with [SCREENSHOT: url] markers"
    }}
  ]
}}

Include {min_sections}-{max_sections} sections. Types: {section_types}."""


class ScriptService:
    def __init__(self, cfg: RuntimeConfig):
        self.cfg = cfg

    async def generate_script(self, research: ResearchResult) -> VideoScript:
        logger.info(f"[Script] Generating for: {research.topic}")
        persona = self.cfg.persona
        target_words = self.cfg.target_minutes * self.cfg.words_per_minute
        raw_cfg = self.cfg._raw

        system = _SYSTEM.format(
            tone=persona["tone"],
            audience=persona["audience"],
            style=persona["style"],
            opener_hook=persona["opener_hook"],
            target_words=target_words,
            target_minutes=self.cfg.target_minutes,
        )
        sections_cfg = raw_cfg["script"]["sections"]
        user = _USER.format(
            topic=research.topic,
            summary=research.structured_summary,
            facts="\n".join(f"• {f}" for f in research.key_facts),
            urls="\n".join(research.relevant_urls[:10]),
            min_sections=sections_cfg["min"],
            max_sections=sections_cfg["max"],
            section_types=", ".join(sections_cfg["allowed_types"]),
        )

        resp = await self.cfg.llm.complete(
            user_prompt=user, system_prompt=system, max_tokens=8192
        )
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.text.strip())
        data = json.loads(raw)
        script = self._parse(research.topic, data)
        logger.info(f"[Script] '{script.title}' — {len(script.sections)} sections, ~{script.total_estimated_seconds/60:.1f}min")
        return script

    def _parse(self, topic: str, data: dict) -> VideoScript:
        sections: list[ScriptSection] = []
        t = 0.0
        for raw in data.get("sections", []):
            narration = raw.get("narration_text", "")
            markers, clean = _extract_markers(narration, raw["section_id"])
            dur = (len(clean.split()) / self.cfg.words_per_minute) * 60
            sections.append(ScriptSection(
                section_id=raw.get("section_id", f"s{len(sections)}"),
                section_type=raw.get("section_type", "main"),
                title=raw.get("title", ""),
                narration_text=clean,
                visual_markers=markers,
                estimated_duration_seconds=dur,
                start_time=t,
            ))
            t += dur
        return VideoScript(
            topic=topic, title=data.get("title", topic),
            sections=sections,
            full_text="\n\n".join(s.narration_text for s in sections),
            total_estimated_seconds=t,
        )


def _extract_markers(narration: str, section_id: str) -> tuple[list[VisualMarker], str]:
    markers = []
    for url in re.findall(r"\[SCREENSHOT:\s*(https?://[^\]]+)\]", narration):
        markers.append(VisualMarker(marker_type="screenshot", url=url.strip(), section_id=section_id))
    for desc in re.findall(r"\[VISUAL:\s*([^\]]+)\]", narration):
        markers.append(VisualMarker(marker_type="visual", description=desc.strip(), section_id=section_id))
    clean = re.sub(r"\[(?:SCREENSHOT|VISUAL):[^\]]*\]", "", narration)
    return markers, re.sub(r"\s+", " ", clean).strip()
