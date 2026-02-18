#!/usr/bin/env python3
"""
YouTube AI Video Pipeline v2 — Config-first CLI & REST API

Usage:
  # Run with defaults from config/pipeline.json
  python -m pipeline.main generate --topic "Claude 4 launched"

  # Use a per-topic override file
  python -m pipeline.main generate --topic-file topics/claude4_launch.json

  # Override specific pipeline.json values inline
  python -m pipeline.main generate --topic "GPT-5" --set llm.provider=openai --set video.style=minimal_white

  # Start REST API
  python -m pipeline.main serve
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .config.loader import ConfigLoader
from .orchestrator import PipelineOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config" / "pipeline.json"


def _apply_set_overrides(cfg_path: Path, set_args: list[str]) -> dict | None:
    """Parse --set key=value args and return as override dict (or None)."""
    if not set_args:
        return None
    overrides = {}
    for item in set_args:
        if "=" not in item:
            raise ValueError(f"--set must be in format key=value, got: {item}")
        k, v = item.split("=", 1)
        # Auto-cast
        if v.lower() == "true":
            v = True
        elif v.lower() == "false":
            v = False
        elif v.replace(".", "").isdigit():
            v = float(v) if "." in v else int(v)
        overrides[k] = v
    return overrides


async def run_generate(args: argparse.Namespace) -> int:
    loader = ConfigLoader(CONFIG_PATH)

    topic_file = Path(args.topic_file) if getattr(args, "topic_file", None) else None
    cfg = loader.load(topic_file)

    # Apply --set overrides (highest priority)
    set_overrides = _apply_set_overrides(CONFIG_PATH, getattr(args, "set", []) or [])
    if set_overrides:
        import json as _json
        raw = _json.loads(CONFIG_PATH.read_text())
        from .config.loader import _set_nested
        for k, v in set_overrides.items():
            _set_nested(raw, k, v)
        cfg = loader._build(raw)

    topic = args.topic
    if not topic and topic_file:
        doc = json.loads(topic_file.read_text())
        topic = doc.get("topic", "")
    if not topic:
        print("ERROR: Provide --topic or --topic-file with a topic field")
        return 1

    for d in [cfg.output_dir, cfg.cache_dir, cfg.temp_dir]:
        Path(d).mkdir(parents=True, exist_ok=True)

    orchestrator = PipelineOrchestrator(cfg)
    result = await orchestrator.run(topic)

    if result.success:
        print(f"\n✅ Success!")
        print(f"   Video    : {result.video_path}")
        print(f"   Metadata : {result.metadata_json_path}")
        if result.metadata:
            print(f"   Title    : {result.metadata.title}")
        return 0
    else:
        print(f"\n❌ Failed: {result.error_message}")
        return 1


async def run_server(args: argparse.Namespace) -> None:
    try:
        from aiohttp import web
    except ImportError:
        print("ERROR: aiohttp required: pip install aiohttp")
        sys.exit(1)

    loader = ConfigLoader(CONFIG_PATH)

    async def handle_generate(req: web.Request) -> web.Response:
        try:
            body = await req.json()
            topic = body.get("topic", "").strip()
            if not topic:
                return web.json_response({"error": "topic required"}, status=400)

            # Support inline overrides from request body
            overrides = body.get("overrides", {})
            cfg = loader.load()
            if overrides:
                import json as _json
                raw = _json.loads(CONFIG_PATH.read_text())
                from .config.loader import _set_nested
                for k, v in overrides.items():
                    _set_nested(raw, k, v)
                cfg = loader._build(raw)

            for d in [cfg.output_dir, cfg.cache_dir, cfg.temp_dir]:
                Path(d).mkdir(parents=True, exist_ok=True)

            result = await PipelineOrchestrator(cfg).run(topic)
            return web.json_response({
                "success": result.success,
                "video_path": str(result.video_path) if result.video_path else None,
                "metadata_path": str(result.metadata_json_path) if result.metadata_json_path else None,
                "error": result.error_message,
                "log": result.pipeline_log,
            })
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def handle_config(_: web.Request) -> web.Response:
        """Return current pipeline.json so clients can inspect active config."""
        return web.json_response(json.loads(CONFIG_PATH.read_text()))

    app = web.Application()
    app.router.add_get("/health", lambda _: web.json_response({"status": "ok"}))
    app.router.add_get("/config", handle_config)
    app.router.add_post("/generate", handle_generate)

    port = int(os.getenv("PORT", "8000"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info(f"Server on http://0.0.0.0:{port}")
    logger.info(f"  POST /generate  — {{ topic, overrides? }}")
    logger.info(f"  GET  /config    — view active pipeline.json")
    await asyncio.Event().wait()


def main() -> None:
    p = argparse.ArgumentParser(description="YouTube AI Video Pipeline v2")
    sub = p.add_subparsers(dest="cmd")

    gen = sub.add_parser("generate", help="Generate a video")
    gen.add_argument("--topic", default="", help="Video topic")
    gen.add_argument("--topic-file", default=None, help="Path to topic override JSON (topics/xxx.json)")
    gen.add_argument("--set", nargs="*", metavar="key=value",
                     help="Override pipeline.json values (e.g. --set llm.provider=openai video.style=minimal_white)")

    serve = sub.add_parser("serve", help="Start REST API")

    args = p.parse_args()

    if args.cmd == "generate":
        sys.exit(asyncio.run(run_generate(args)))
    elif args.cmd == "serve":
        asyncio.run(run_server(args))
    else:
        p.print_help()


if __name__ == "__main__":
    main()
