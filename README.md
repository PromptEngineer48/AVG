# 🎬 YouTube AI Video Pipeline v2 — Zero-Code Config

**Change providers, styles, voices, and behaviour by editing one JSON file.**
No code changes. Ever.

---

## The Two Files You Touch

| File | What it controls |
|---|---|
| `.env` | API keys only (secrets) |
| `config/pipeline.json` | Everything else |

That's it. No Python editing required.

---

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt
playwright install chromium && playwright install-deps chromium
sudo apt-get install ffmpeg fonts-dejavu-core

# 2. Set API keys
cp .env.example .env
nano .env   # Fill in keys for whichever providers you use

# 3. Edit config/pipeline.json to choose providers + style
# (or leave defaults)

# 4. Run
python -m pipeline.main generate --topic "Claude 4 just launched"
```

---

## Switching Providers (zero code)

### Switch LLM
Edit `config/pipeline.json`:
```json
"llm": { "provider": "openai" }
```
Supported: `claude` | `openai` | `gemini`

### Switch Search
```json
"search": { "provider": "bing" }
```
Supported: `google` | `bing` | `serpapi` | `searx` (free, self-hosted)

### Switch Voice
```json
"voice": { "provider": "openai_tts" }
```
Supported: `elevenlabs` | `openai_tts` | `azure`

### Switch Video Style
```json
"video": { "style": "minimal_white" }
```
Styles: `dark_tech` | `minimal_white` | `news_room`

### Switch Script Persona
```json
"script": { "persona": "hype" }
```
Personas: `tech_enthusiast` | `educator` | `hype` | `analyst`

---

## Per-Topic Overrides

Create `topics/my_topic.json`:
```json
{
  "topic": "OpenAI o3 release",
  "overrides": {
    "llm.provider": "openai",
    "script.persona": "hype",
    "script.target_minutes": 8,
    "video.style": "news_room",
    "voice.provider": "openai_tts"
  }
}
```

Run it:
```bash
python -m pipeline.main generate --topic-file topics/my_topic.json
```

---

## CLI Inline Overrides

No file needed — override on the fly:
```bash
python -m pipeline.main generate \
  --topic "Google Gemini Ultra 2" \
  --set llm.provider=gemini \
  --set video.style=minimal_white \
  --set script.target_minutes=8
```

---

## REST API

```bash
python -m pipeline.main serve
```

**Generate a video:**
```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "GPT-5 just dropped",
    "overrides": {
      "llm.provider": "openai",
      "script.persona": "hype",
      "video.style": "dark_tech"
    }
  }'
```

**Inspect active config:**
```bash
curl http://localhost:8000/config
```

---

## Adding a New Provider (Developers Only)

Want to add, say, Mistral as an LLM?

1. Create `providers/llm/mistral_provider.py` — implement `BaseLLMProvider`
2. Add one line to `config/loader.py` in `_build_llm_provider()`:
   ```python
   elif name == "mistral":
       from ..providers.llm.mistral_provider import MistralProvider
       return MistralProvider(model)
   ```
3. Add entry to `config/pipeline.json`:
   ```json
   "llm": { "model": { "mistral": "mistral-large-latest" } }
   ```

That's the **only** code change needed. All services automatically use the new provider.

---

## Project Structure

```
pipeline/
├── config/
│   ├── pipeline.json          ← THE config file (edit this)
│   └── loader.py              ← reads JSON, builds RuntimeConfig
├── providers/
│   ├── llm/                   ← claude, openai, gemini
│   ├── search/                ← google, bing, serpapi, searx
│   └── voice/                 ← elevenlabs, openai_tts, azure
├── services/                  ← business logic (no provider imports)
│   ├── research_service.py
│   ├── script_service.py
│   ├── visual_service.py
│   ├── voice_service.py
│   ├── sync_service.py
│   ├── video_service.py
│   └── metadata_service.py
├── topics/                    ← per-topic override JSONs
├── main.py                    ← CLI + REST API
├── orchestrator.py            ← pipeline coordination
└── .env                       ← API keys only
```

---

## Full `pipeline.json` Reference

| Path | Default | Options |
|---|---|---|
| `llm.provider` | `claude` | `claude` `openai` `gemini` |
| `search.provider` | `google` | `google` `bing` `serpapi` `searx` |
| `voice.provider` | `elevenlabs` | `elevenlabs` `openai_tts` `azure` |
| `video.style` | `dark_tech` | `dark_tech` `minimal_white` `news_room` |
| `script.persona` | `tech_enthusiast` | `tech_enthusiast` `educator` `hype` `analyst` |
| `script.target_minutes` | `12` | any integer |
| `video.transitions.type` | `fade` | `fade` `slideleft` `slideright` `wipeleft` `dissolve` |
| `video.background_music.enabled` | `false` | `true` `false` |
| `quality_checks.enabled` | `true` | `true` `false` |

To add a **new style**, **new persona**, or **new transition** — just add a new entry in `pipeline.json`. No code needed.
