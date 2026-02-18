"""
Pipeline Orchestrator (v2 — config-driven)
All wiring comes from RuntimeConfig; zero hardcoded provider names.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from .config.loader import ConfigLoader, RuntimeConfig
from .services.metadata_service import MetadataService
from .services.research_service import ResearchService
from .services.script_service import ScriptService
from .services.sync_service import SyncService
from .services.video_service import VideoAssemblyService
from .services.visual_service import VisualService
from .services.voice_service import VoiceService
from .utils.models import PipelineResult

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(self, cfg: RuntimeConfig):
        self.cfg = cfg
        self.research  = ResearchService(cfg)
        self.script    = ScriptService(cfg)
        self.visual    = VisualService(cfg)
        self.voice     = VoiceService(cfg)
        self.sync      = SyncService(cfg)
        self.video     = VideoAssemblyService(cfg)
        self.metadata  = MetadataService(cfg)

    async def run(self, topic: str) -> PipelineResult:
        result = PipelineResult(topic=topic)
        t0 = time.time()

        def log(msg):
            logger.info(msg)
            result.pipeline_log.append(msg)

        try:
            log(f"━━━ Pipeline: '{topic}' | LLM={self.cfg.llm.provider_name} "
                f"Search={self.cfg.search.provider_name} Voice={self.cfg.voice.provider_name} ━━━")

            log("1/7 Research…")
            research = await self.research.research(topic)
            log(f"  ✓ {len(research.key_facts)} facts, {len(research.findings)} sources")

            log("2/7 Script…")
            script_obj = await self.script.generate_script(research)
            log(f"  ✓ '{script_obj.title}' — {len(script_obj.sections)} sections")

            log("3/7 Visuals…")
            raw_visuals = await self.visual.collect_visuals(script_obj)
            log(f"  ✓ {len(raw_visuals)} assets")
            if self.cfg.quality_checks_enabled and len(raw_visuals) < self.cfg.min_visual_assets:
                log(f"  ⚠ Only {len(raw_visuals)} visual assets (min {self.cfg.min_visual_assets})")

            log("4/7 Voice…")
            chunks = await self.voice.synthesise_script(script_obj)
            log(f"  ✓ {sum(c.duration_seconds for c in chunks):.1f}s")

            log("5/7 Sync…")
            timed = self.sync.assign_timings(script_obj, chunks, raw_visuals)
            log(f"  ✓ {len(timed)} assets timed")

            log("6/7 Video assembly…")
            stem = _safe_stem(script_obj.title)
            video_path = await self.video.assemble(chunks, timed, stem)
            log(f"  ✓ {video_path}")

            log("7/7 Metadata…")
            meta = await self.metadata.generate(script_obj, research)
            meta_path = Path(self.cfg.output_dir) / f"{stem}_metadata.json"
            meta_path.write_text(json.dumps({
                "title": meta.title, "description": meta.description,
                "tags": meta.tags, "category": meta.category,
                "thumbnail_suggestions": meta.thumbnail_suggestions,
            }, indent=2))
            log(f"  ✓ {meta_path}")

            log(f"━━━ Done in {time.time()-t0:.1f}s ━━━")
            result.video_path = video_path
            result.metadata = meta
            result.metadata_json_path = meta_path
            result.success = True

        except Exception as exc:
            logger.exception(f"[Pipeline] Fatal: {exc}")
            result.error_message = str(exc)
            result.success = False

        return result


def _safe_stem(title: str) -> str:
    s = re.sub(r"[^\w\s-]", "", title)
    return re.sub(r"\s+", "_", s.strip())[:80] or "video"
