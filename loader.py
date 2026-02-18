"""
Config Loader
──────────────
Reads pipeline.json, applies per-topic overrides (dot-notation paths),
resolves API keys from environment, and instantiates all providers.

This is the ONLY file that knows about providers and config structure.
All services receive a RuntimeConfig object and never touch JSON or env directly.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..providers.llm.base import BaseLLMProvider
from ..providers.search.providers import BaseSearchProvider, get_search_provider
from ..providers.voice.providers import BaseVoiceProvider, get_voice_provider

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "pipeline.json"


# ── Runtime config dataclass (what services actually use) ─────────────────────

@dataclass
class RuntimeConfig:
    # Providers (instantiated, ready to use)
    llm:    BaseLLMProvider
    search: BaseSearchProvider
    voice:  BaseVoiceProvider

    # Script settings
    target_minutes:   int
    words_per_minute: int
    persona:          dict   # full persona dict from pipeline.json

    # Video style (resolved from style name)
    video_style:      dict

    # Transition
    transition_type:     str
    transition_duration: float

    # Screenshot
    screenshot_display_duration: float

    # Background music
    bg_music_enabled: bool
    bg_music_path:    str
    bg_music_volume:  float

    # Voice raw settings dict (passed to provider.synthesise)
    voice_settings:   dict

    # Output
    output_dir:    str
    cache_dir:     str
    temp_dir:      str
    video_codec:   str
    audio_codec:   str
    audio_bitrate: str
    ffmpeg_preset: str

    # Metadata
    metadata_category:    str
    metadata_language:    str
    metadata_default_tags: list[str]
    metadata_max_tags:    int

    # Quality checks
    quality_checks_enabled:   bool
    max_sync_drift_sec:       float
    min_visual_assets:        int
    abort_on_tts_failure:     bool

    # Raw config (for anything not explicitly mapped)
    _raw: dict = field(default_factory=dict, repr=False)

    @property
    def canvas_width(self) -> int:
        return self.video_style["canvas"]["width"]

    @property
    def canvas_height(self) -> int:
        return self.video_style["canvas"]["height"]

    @property
    def fps(self) -> int:
        return self.video_style["fps"]


# ── Loader ────────────────────────────────────────────────────────────────────

class ConfigLoader:
    def __init__(self, config_path: Path = _DEFAULT_CONFIG_PATH):
        self._path = config_path

    def load(self, topic_override_path: Optional[Path] = None) -> RuntimeConfig:
        """
        Load pipeline.json, apply optional per-topic overrides, resolve providers.
        """
        cfg = json.loads(self._path.read_text())
        logger.debug(f"[Config] Loaded base config from {self._path}")

        # Apply per-topic overrides (dot-notation keys)
        if topic_override_path and topic_override_path.exists():
            overrides_doc = json.loads(topic_override_path.read_text())
            overrides = overrides_doc.get("overrides", {})
            for dot_key, value in overrides.items():
                _set_nested(cfg, dot_key, value)
            logger.info(
                f"[Config] Applied {len(overrides)} overrides "
                f"from {topic_override_path.name}"
            )

        return self._build(cfg)

    def _build(self, cfg: dict) -> RuntimeConfig:
        # ── LLM ──────────────────────────────────────────────────────────────
        llm_provider_name = cfg["llm"]["provider"]
        llm_model = cfg["llm"]["model"][llm_provider_name]
        llm = _build_llm_provider(llm_provider_name, llm_model)
        logger.info(f"[Config] LLM: {llm_provider_name} / {llm_model}")

        # ── Search ────────────────────────────────────────────────────────────
        search_name = cfg["search"]["provider"]
        search = get_search_provider(search_name)
        logger.info(f"[Config] Search: {search_name}")

        # ── Voice ─────────────────────────────────────────────────────────────
        voice_name = cfg["voice"]["provider"]
        voice_model = cfg["voice"]["model"][voice_name]
        voice = get_voice_provider(voice_name, voice_model)
        voice_settings = cfg["voice"]["settings"].get(voice_name, {})
        logger.info(f"[Config] Voice: {voice_name} / {voice_model}")

        # ── Video style ───────────────────────────────────────────────────────
        style_name = cfg["video"]["style"]
        video_style = cfg["video"]["styles"][style_name]
        logger.info(f"[Config] Video style: {style_name}")

        # ── Script persona ────────────────────────────────────────────────────
        persona_name = cfg["script"]["persona"]
        persona = cfg["script"]["personas"][persona_name]

        # ── Output ────────────────────────────────────────────────────────────
        out = cfg["output"]
        qc = cfg.get("quality_checks", {})
        meta = cfg.get("metadata", {})
        trans = cfg["video"]["transitions"]
        bgm = cfg["video"]["background_music"]

        return RuntimeConfig(
            llm=llm,
            search=search,
            voice=voice,
            target_minutes=cfg["script"]["target_minutes"],
            words_per_minute=cfg["script"]["words_per_minute"],
            persona=persona,
            video_style=video_style,
            transition_type=trans.get("type", "fade"),
            transition_duration=trans.get("duration", 0.5),
            screenshot_display_duration=cfg["video"].get("screenshot_display_duration", 8),
            bg_music_enabled=bgm.get("enabled", False),
            bg_music_path=bgm.get("path", ""),
            bg_music_volume=bgm.get("volume", 0.08),
            voice_settings=voice_settings,
            output_dir=out.get("dir", "./output"),
            cache_dir=out.get("cache_dir", "./cache"),
            temp_dir=out.get("temp_dir", "./temp"),
            video_codec=out.get("video_codec", "libx264"),
            audio_codec=out.get("audio_codec", "aac"),
            audio_bitrate=out.get("audio_bitrate", "192k"),
            ffmpeg_preset=out.get("preset", "fast"),
            metadata_category=meta.get("category", "Science & Technology"),
            metadata_language=meta.get("language", "en"),
            metadata_default_tags=meta.get("default_tags", []),
            metadata_max_tags=meta.get("max_tags", 20),
            quality_checks_enabled=qc.get("enabled", True),
            max_sync_drift_sec=qc.get("max_sync_drift_sec", 2.0),
            min_visual_assets=qc.get("min_visual_assets", 3),
            abort_on_tts_failure=qc.get("abort_on_tts_failure", True),
            _raw=cfg,
        )


# ── LLM factory ───────────────────────────────────────────────────────────────

def _build_llm_provider(name: str, model: str) -> BaseLLMProvider:
    name = name.lower()
    if name == "claude":
        from ..providers.llm.claude_provider import ClaudeProvider
        return ClaudeProvider(model)
    elif name == "openai":
        from ..providers.llm.openai_provider import OpenAIProvider
        return OpenAIProvider(model)
    elif name == "gemini":
        from ..providers.llm.gemini_provider import GeminiProvider
        return GeminiProvider(model)
    else:
        raise ValueError(
            f"Unknown LLM provider '{name}'. Supported: claude, openai, gemini"
        )


# ── Dot-notation nested key setter ────────────────────────────────────────────

def _set_nested(d: dict, dot_key: str, value: Any) -> None:
    """Set d["a"]["b"]["c"] = value from dot_key="a.b.c"."""
    keys = dot_key.split(".")
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value
