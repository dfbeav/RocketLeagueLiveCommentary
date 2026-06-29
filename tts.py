"""
tts.py — Sends text to ElevenLabs streaming TTS and plays the audio.
Uses a background thread + queue so the main loop never blocks on audio.

Announcer 1 has priority: when a call for Announcer 1 arrives, any pending
items in the queue are discarded so the new lines play next (after whatever
is currently mid-playback finishes).

Initialises pygame.mixer automatically on first use so callers don't need
to call init() explicitly.
"""

import io
import json
import queue
import threading
import requests
import pygame
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID_1, ELEVENLABS_VOICE_ID_2

_HEADERS = {
    "xi-api-key": ELEVENLABS_API_KEY,
    "Content-Type": "application/json",
}

_TTS_BODY = {
    "model_id": "eleven_turbo_v2",
    "voice_settings": {
        "stability": 0.3,
        "similarity_boost": 0.8,
        "style": 0.7,
        "use_speaker_boost": True,
    },
    "optimize_streaming_latency": 1,
}

_ANNOUNCER_VOLUMES = {
    1: 1.0,
    2: 0.6,
}

# ── Audio queue ───────────────────────────────────────────────────────────────
_audio_queue: queue.Queue[tuple[str, int, int] | None] = queue.Queue()
_worker_thread: threading.Thread | None = None
_initialized = False
_init_lock = threading.Lock()

# Generation counter — incremented each time the queue is flushed for
# Announcer 1 priority. The worker checks this before playing each item
# so any items that were already dequeued but belong to a stale generation
# are silently dropped.
_generation: int = 0
_generation_lock = threading.Lock()


def _ensure_init():
    """Initialise pygame mixer and start the worker thread if not already done."""
    global _initialized, _worker_thread
    with _init_lock:
        if not _initialized:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            _worker_thread = threading.Thread(target=_worker, daemon=True)
            _worker_thread.start()
            _initialized = True
            print("[TTS] Audio system ready.")


def _extract_texts(content_blocks) -> list[str]:
    """
    Accept either:
      - a list of Anthropic ContentBlock objects  (have a .text attribute)
      - a list of plain strings
      - a JSON string encoding a list of lines     (the announcer prompt format)

    Returns a flat list of non-empty strings ready for TTS.
    """
    texts: list[str] = []

    for block in content_blocks:
        # Plain string passed directly
        if isinstance(block, str):
            raw = block.strip()
        # Anthropic SDK ContentBlock (TextBlock has .text; ToolUseBlock etc. don't)
        elif hasattr(block, "text"):
            raw = block.text.strip()
        else:
            continue

        if not raw:
            continue

        # The announcer prompts instruct the model to reply as a JSON array,
        # e.g. ["Great goal!", "Orange is really struggling."]
        # Strip markdown code fences in case the model wraps the JSON in them.
        stripped = raw
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1]  # drop the opening ```json line
        if stripped.endswith("```"):
            stripped = stripped.rsplit("```", 1)[0]  # drop the closing ```
        stripped = stripped.strip()

        # Try to parse that so each sentence becomes a separate TTS item.
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                texts.extend(str(item).strip() for item in parsed if str(item).strip())
                continue
        except (json.JSONDecodeError, TypeError):
            pass

        texts.append(raw)

    return texts


def _clear_queue():
    """Drain all pending items from the queue without blocking."""
    while True:
        try:
            _audio_queue.get_nowait()
            _audio_queue.task_done()
        except queue.Empty:
            break


def _fetch_and_play(text: str, announcer: int):
    """Fetch audio from ElevenLabs and play it via pygame."""
    print(f"[TTS] Fetching and playing (Announcer {announcer}): {text!r}")
    try:
        body = {**_TTS_BODY, "text": text}
        voice_id = ELEVENLABS_VOICE_ID_1 if announcer == 1 else ELEVENLABS_VOICE_ID_2
        tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"

        response = requests.post(tts_url, headers=_HEADERS, json=body, stream=True, timeout=10)
        response.raise_for_status()

        audio_data = b"".join(response.iter_content(chunk_size=4096))
        audio_buffer = io.BytesIO(audio_data)

        sound = pygame.mixer.Sound(audio_buffer)
        sound.set_volume(_ANNOUNCER_VOLUMES.get(announcer, 1.0))

        channel = sound.play()

        # Wait for playback to finish.
        while channel and channel.get_busy():
            pygame.time.wait(50)

    except Exception as e:
        print(f"[TTS] Error: {e}")


def _worker():
    """Background thread that drains the audio queue one item at a time."""
    while True:
        item = _audio_queue.get()

        if item is None:
            # Shutdown signal.
            break

        text, announcer, item_generation = item

        # Check whether this item still belongs to the current generation
        # before spending time fetching + playing it.
        with _generation_lock:
            current_generation = _generation

        if item_generation < current_generation:
            print(f"[TTS] Dropping stale item (gen {item_generation} < {current_generation}): {text!r}")
            _audio_queue.task_done()
            continue

        _fetch_and_play(text, announcer)
        _audio_queue.task_done()


def speak(content_blocks, announcer: int):
    """
    Queue lines for TTS playback. Returns immediately — audio plays in the
    background.

    `content_blocks` can be:
      - a list of Anthropic ContentBlock objects (the raw agent response)
      - a list of plain strings
      - a single string

    If announcer == 1, any items already waiting in the queue are discarded
    first so the new lines play as soon as the current audio finishes.
    """
    _ensure_init()

    # Normalise a bare string so _extract_texts can iterate it as a list.
    if isinstance(content_blocks, str):
        content_blocks = [content_blocks]

    texts = _extract_texts(content_blocks)
    if not texts:
        return

    global _generation

    print(f"🗣️ [TTS] New content blocks for Announcer {announcer}: {texts}")

    if announcer == 1:
        with _generation_lock:
            _generation += 1
            current_generation = _generation
        _clear_queue()
        print(f"[TTS] Announcer 1 priority — queue cleared (gen → {current_generation}).")
    else:
        with _generation_lock:
            current_generation = _generation

    for text in texts:
        print(f"[TTS] Queuing (Announcer {announcer}): {text!r}")
        _audio_queue.put((text, announcer, current_generation))


def set_volume(announcer: int, volume: float):
    """Adjust an announcer's volume between 0.0 and 1.0."""
    _ANNOUNCER_VOLUMES[announcer] = max(0.0, min(1.0, volume))


def shutdown():
    _audio_queue.put(None)
    if _worker_thread:
        _worker_thread.join(timeout=5)
    pygame.mixer.quit()