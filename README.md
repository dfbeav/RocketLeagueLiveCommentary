# Rocket League Live Commentary

Real-time Rocket League commentary driven by the local Rocket League event feed, Anthropic, and optional ElevenLabs text-to-speech.

## What It Does

- Connects to the Rocket League event source on `127.0.0.1:49123`
- Generates announcer lines with Anthropic via `langchain`
- Optionally plays audio using ElevenLabs and `pygame`

## Requirements

- Python 3.12 or newer
- A populated `.env` file
- Internet access for API calls
- A running Rocket League event feed that exposes data on `127.0.0.1:49123`

## Setup

1. Copy `.env.example` to `.env`.
2. Fill in your API keys:
   - `ANTHROPIC_API_KEY`
   - `ELEVENLABS_API_KEY`
3. Install the Python packages:
   - run: `python -m pip install -r requirements.txt`

## Run

1. Run Rocket League

2. Run the
```bash
python main.py
```

## Notes

- Audio generation is controlled in `config.py` with `ENABLE_AUDIO_GENERATION`.
- If you only want text output, keep audio generation disabled.
- The app will start, but it will not commentate anything until the Rocket League event source is active.

## Project Files

- `main.py` - event loop and match handling
- `announcer.py` - LangChain / Anthropic setup
- `tts.py` - ElevenLabs audio playback
- `config.py` - API keys and feature flags
- `state.py` - shared runtime state
- `.env.example` - environment variable template
- `install_deps.bat` - Windows dependency installer