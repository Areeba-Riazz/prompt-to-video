"""
Voice Synthesis — models/voice_synth.py
MCP Tool Name: voice_cloning_synthesizer

Priority chain:
  1. CosyVoice2       — voice cloning with reference audio (requires external_models/CosyVoice)
  2. HF Inference API — facebook/mms-tts-eng via HF_TOKEN (free, no local GPU/torch needed)
  3. Kokoro TTS       — high quality local TTS (requires compatible torch+transformers)
  4. Local tone WAV   — pure-Python fallback (always works, stdlib only)
"""

import math
import os
import struct
import wave
from typing import Optional


def _hf_token() -> str:
    """Return HF token — accepts both guide name (HF_TOKEN) and legacy name (HF_API_TOKEN)."""
    return (
        os.getenv("HF_TOKEN", "").strip()
        or os.getenv("HF_API_TOKEN", "").strip()
    )


# ─────────────────────────────────────────────────────────────────────────────
# Engine 1: CosyVoice2 (voice cloning — best quality)
# ─────────────────────────────────────────────────────────────────────────────

def _synthesize_with_cosyvoice(
    text: str,
    speaker_reference_audio: str,
    output_path: str,
    emotion: str = "neutral",
) -> str:
    """
    Clone voice from a reference WAV and synthesize new speech.
    Requires external_models/CosyVoice cloned and its requirements installed.
    """
    import sys

    cosyvoice_dir = os.path.join(os.getcwd(), "external_models", "CosyVoice")
    sys.path.insert(0, cosyvoice_dir)

    from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore
    from cosyvoice.utils.file_utils import load_wav  # type: ignore
    import numpy as np
    import soundfile as sf

    model = CosyVoice2(
        "pretrained_models/CosyVoice2-0.5B",
        load_jit=True,
        load_trt=False,
        fp16=True,
    )

    ref_audio, _ = load_wav(speaker_reference_audio, 16000)

    emotion_map = {
        "neutral": "Speak clearly and naturally.",
        "happy": "Speak with warmth and enthusiasm.",
        "sad": "Speak slowly with a somber tone.",
        "angry": "Speak with urgency and tension.",
        "fearful": "Speak with hesitation and anxiety.",
    }
    instruct = emotion_map.get(emotion, emotion_map["neutral"])

    output = model.inference_zero_shot(
        tts_text=text,
        prompt_text="",
        prompt_speech_16k=ref_audio,
        stream=False,
    )

    combined = np.concatenate([seg["tts_speech"].numpy() for seg in output])
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sf.write(output_path, combined, 22050)
    print(f"[VoiceSynth] CosyVoice2 output saved to {output_path}")
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# Engine 2: HuggingFace Inference API (MMS-TTS — no local GPU needed)
# ─────────────────────────────────────────────────────────────────────────────

def _synthesize_with_edge_tts(
    text: str,
    output_path: str,
    character_name: str = "A",
    emotion: str = "neutral",
) -> str:
    """
    Engine 2: Microsoft Edge TTS via edge-tts library.
    Free, high-quality neural voices, no API key or credits needed.
    Requires: pip install edge-tts
    Saves as MP3 (renamed to .wav extension — Wav2Lip accepts both).
    """
    import asyncio
    import edge_tts  # type: ignore

    # Voice mapping per character: male/female neural voices
    voice_map = {
        "Kael": "en-US-GuyNeural",
        "Sora": "en-US-JennyNeural",
        "Warden AI": "en-GB-RyanNeural",
        "A": "en-US-GuyNeural",
        "B": "en-US-JennyNeural",
        "C": "en-GB-RyanNeural",
        "D": "en-AU-WilliamNeural",
    }
    voice = voice_map.get(character_name, "en-US-JennyNeural")

    # Emotion to playback speed mapping
    emotion_rates = {
        "angry": "+20%",
        "happy": "+10%",
        "neutral": "+0%",
        "calm": "-10%",
        "sad": "-15%",
        "fearful": "+15%",
    }
    rate = emotion_rates.get(emotion.lower(), "+0%")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Save to a temp MP3 first (edge-tts native format), then convert to WAV
    mp3_path = output_path.replace(".wav", ".mp3") if output_path.endswith(".wav") else output_path + ".mp3"

    async def _run():
        tts = edge_tts.Communicate(text, voice=voice, rate=rate)
        await tts.save(mp3_path)

    asyncio.run(_run())

    # Convert MP3 → WAV so Wav2Lip can process it
    if output_path.endswith(".wav"):
        try:
            import subprocess as _sp, sys as _sys
            _sp.run(
                ["ffmpeg", "-y", "-i", mp3_path, "-ar", "16000", "-ac", "1", output_path],
                check=True, capture_output=True
            )
            os.remove(mp3_path)
        except Exception:
            # ffmpeg not available — rename MP3 as the output (Wav2Lip handles some MP3 too)
            os.replace(mp3_path, output_path)
    else:
        os.replace(mp3_path, output_path)

    size = os.path.getsize(output_path)
    print(f"[VoiceSynth] edge-tts ({voice}, rate={rate}) saved to {output_path} ({size:,} bytes)")
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# Engine 3: Kokoro TTS (high quality local — requires compatible torch)
# ─────────────────────────────────────────────────────────────────────────────

_VOICE_MAP = {
    "Kael": "am_adam",
    "Sora": "af_sarah",
    "Warden AI": "bf_emma",
    "A": "am_adam",
    "B": "af_sarah",
    "C": "bf_emma",
    "D": "bm_george",
}


def _synthesize_with_kokoro(
    text: str,
    output_path: str,
    character_name: str = "A",
) -> str:
    """
    Kokoro TTS. High quality, no reference audio needed.
    Requires: pip install kokoro>=0.9.4  AND  compatible torch + transformers.
    """
    from kokoro import KPipeline  # type: ignore
    import numpy as np
    import soundfile as sf

    voice = _VOICE_MAP.get(character_name, "af_sarah")
    pipeline = KPipeline(lang_code="a")
    audio_segments = []

    generator = pipeline(text, voice=voice, speed=1.0, split_pattern=r"\n+")
    for _, _, audio in generator:
        audio_segments.append(audio)

    combined = np.concatenate(audio_segments)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    sf.write(output_path, combined, 24000)
    print(f"[VoiceSynth] Kokoro ({voice}) saved to {output_path}")
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# Engine 4: Local tone WAV — always works (stdlib only)
# ─────────────────────────────────────────────────────────────────────────────

def _synthesize_tone_wav(text: str, output_path: str) -> str:
    """
    Pure-Python fallback: sine-wave tone proportional to text length.
    Uses only stdlib wave + struct + math — zero external dependencies.
    """
    framerate = 22050
    duration = max(1.5, min(8.0, len(text) / 18.0))
    freq = 200 + (len(text) % 180)
    amplitude = 12000
    n_samples = int(duration * framerate)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with wave.open(output_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        for i in range(n_samples):
            val = int(amplitude * math.sin(2 * math.pi * freq * (i / framerate)))
            wf.writeframesraw(struct.pack("<h", val))
    print(f"[VoiceSynth] Tone fallback saved to {output_path}")
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point — registered as MCP tool
# ─────────────────────────────────────────────────────────────────────────────

def synthesize_voice(
    character_name: str,
    dialogue: str,
    output_path: str,
    reference_audio_path: Optional[str] = None,
    emotion: str = "neutral",
) -> str:
    """
    Main entry point for the MCP voice_cloning_synthesizer tool.
    Tries engines: CosyVoice2 → edge-tts → Kokoro → tone WAV.

    Args:
        character_name: Character identifier (e.g. 'Kael', 'Sora').
        dialogue: The line of dialogue to synthesize.
        output_path: Path to save the output WAV file.
        reference_audio_path: Optional 3-10 s WAV clip for CosyVoice2.
        emotion: One of neutral, happy, sad, angry, fearful.

    Returns:
        Path to the generated WAV file.
    """
    if os.path.dirname(output_path):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Engine 1: CosyVoice2 (needs reference audio + cloned model)
    if reference_audio_path and os.path.exists(reference_audio_path):
        try:
            return _synthesize_with_cosyvoice(dialogue, reference_audio_path, output_path, emotion)
        except Exception as e:
            print(f"[VoiceSynth] CosyVoice2 failed: {e}. Trying edge-tts...")

    # Engine 2: edge-tts — free Microsoft neural voices, no API key needed
    try:
        return _synthesize_with_edge_tts(dialogue, output_path, character_name)
    except Exception as e:
        print(f"[VoiceSynth] edge-tts failed: {e}. Trying Kokoro...")

    # Engine 3: Kokoro (needs compatible torch + transformers)
    try:
        return _synthesize_with_kokoro(dialogue, output_path, character_name)
    except Exception as e:
        print(f"[VoiceSynth] Kokoro failed: {e}. Using tone fallback...")

    # Engine 4: Always works
    return _synthesize_tone_wav(dialogue, output_path)
