import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID_1 = os.getenv("ELEVENLABS_VOICE_ID_1", "")
ELEVENLABS_VOICE_ID_2 = os.getenv("ELEVENLABS_VOICE_ID_2", "")

# ── Enable/Disable Announcers ──────────────────────────────────────────────────
ENABLE_ANNOUNCER_1 = True  # set to False to disable announcer 1
ENABLE_ANNOUNCER_2 = True  # set to False to disable announcer 2

ENABLE_AUDIO_GENERATION = True