import math
import os
import struct
import wave
from typing import Any, Dict, Optional, Tuple

from mcp.base_tool import BaseTool
from shared.utils.voice_mapping import edge_voice_for_character, kokoro_voice_for_character


def _edge_prosody(emotion: str) -> Tuple[str, str, str]:
    """rate, pitch, volume for edge-tts Communicate()."""
    e = (emotion or "neutral").lower()
    rates = {
        "angry": "+18%",
        "happy": "+10%",
        "neutral": "+0%",
        "calm": "-12%",
        "sad": "-18%",
        "fearful": "+12%",
    }
    pitches = {
        "angry": "+12Hz",
        "happy": "+8Hz",
        "neutral": "+0Hz",
        "calm": "-10Hz",
        "sad": "-15Hz",
        "fearful": "+22Hz",
    }
    volumes = {
        "angry": "+8%",
        "happy": "+4%",
        "neutral": "+0%",
        "calm": "-6%",
        "sad": "-4%",
        "fearful": "+2%",
    }
    return rates.get(e, "+0%"), pitches.get(e, "+0Hz"), volumes.get(e, "+0%")


def _kokoro_speed(emotion: str) -> float:
    e = (emotion or "neutral").lower()
    return {
        "angry": 1.07,
        "happy": 1.05,
        "neutral": 1.0,
        "calm": 0.9,
        "sad": 0.86,
        "fearful": 1.08,
    }.get(e, 1.0)


def _hf_token() -> str:
    """Return HF token."""
    return os.getenv("HF_TOKEN", "").strip() or os.getenv("HF_API_TOKEN", "").strip()

def _synthesize_with_cosyvoice(text: str, speaker_reference_audio: str, output_path: str, emotion: str = "neutral") -> str:
    import sys
    cosyvoice_dir = os.path.join(os.getcwd(), "external_models", "CosyVoice")
    sys.path.insert(0, cosyvoice_dir)
    from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore
    from cosyvoice.utils.file_utils import load_wav  # type: ignore
    import numpy as np
    import soundfile as sf

    model = CosyVoice2("pretrained_models/CosyVoice2-0.5B", load_jit=True, load_trt=False, fp16=True)
    ref_audio, _ = load_wav(speaker_reference_audio, 16000)
    emotion_map = {
        "neutral": "Speak clearly and naturally.",
        "happy": "Speak with warmth and enthusiasm.",
        "sad": "Speak slowly with a somber tone.",
        "angry": "Speak with urgency and tension.",
        "fearful": "Speak with hesitation and anxiety.",
    }
    instruct = emotion_map.get(emotion, emotion_map["neutral"])
    output = model.inference_zero_shot(tts_text=text, prompt_text="", prompt_speech_16k=ref_audio, stream=False)
    combined = np.concatenate([seg["tts_speech"].numpy() for seg in output])
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    sf.write(output_path, combined, 22050)
    print(f"[VoiceSynth] CosyVoice2 output saved to {output_path}")
    return output_path

def _synthesize_with_edge_tts(
    text: str,
    output_path: str,
    character_name: str = "A",
    emotion: str = "neutral",
    *,
    gender: Optional[str] = None,
    edge_voice: Optional[str] = None,
) -> str:
    import asyncio
    import edge_tts  # type: ignore

    voice = edge_voice_for_character(
        character_name or "Narrator",
        gender=gender,
        edge_voice=edge_voice,
    )
    rate, pitch, volume = _edge_prosody(emotion)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    mp3_path = output_path.replace(".wav", ".mp3") if output_path.endswith(".wav") else output_path + ".mp3"

    async def _run():
        tts = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch, volume=volume)
        await tts.save(mp3_path)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run())
    else:
        import concurrent.futures

        def _edge_worker() -> None:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(_run())
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(_edge_worker).result()
    if output_path.endswith(".wav"):
        try:
            import subprocess as _sp
            _sp.run(["ffmpeg", "-y", "-i", mp3_path, "-ar", "16000", "-ac", "1", output_path], check=True, capture_output=True)
            os.remove(mp3_path)
        except Exception:
            os.replace(mp3_path, output_path)
    else:
        os.replace(mp3_path, output_path)
    print(f"[VoiceSynth] edge-tts ({voice}, emotion={emotion}, rate={rate}, pitch={pitch}) saved to {output_path}")
    return output_path


def _synthesize_with_kokoro(
    text: str,
    output_path: str,
    character_name: str = "A",
    emotion: str = "neutral",
    *,
    gender: Optional[str] = None,
    kokoro_voice: Optional[str] = None,
) -> str:
    from kokoro import KPipeline  # type: ignore
    import numpy as np
    import soundfile as sf

    voice = kokoro_voice_for_character(
        character_name or "Narrator",
        gender=gender,
        kokoro_voice=kokoro_voice,
    )
    speed = _kokoro_speed(emotion)
    pipeline = KPipeline(lang_code="a")
    audio_segments = []
    generator = pipeline(text, voice=voice, speed=speed, split_pattern=r"\n+")
    for _, _, audio in generator:
        audio_segments.append(audio)
    combined = np.concatenate(audio_segments)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    sf.write(output_path, combined, 24000)
    print(f"[VoiceSynth] Kokoro ({voice}, speed={speed}) saved to {output_path}")
    return output_path

def _synthesize_tone_wav(text: str, output_path: str) -> str:
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

class VoiceSynthesisTool(BaseTool):
    @property
    def name(self) -> str:
        return "voice_cloning_synthesizer"

    @property
    def description(self) -> str:
        return (
            "Synthesizes dialogue speech using CosyVoice2 voice cloning (primary), "
            "Kokoro TTS (fallback), or local tone WAV (always available)."
        )

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "character_name": "str — character identifier",
            "dialogue": "str — line of dialogue to synthesize",
            "output_path": "str — path to save output WAV",
            "reference_audio_path": "str | None — optional 3-10s voice reference WAV",
            "emotion": "str — neutral | happy | sad | angry | fearful | calm",
            "gender": "str | None — male | female | neutral (optional; improves Edge/Kokoro voice pick)",
            "edge_voice": "str | None — explicit Edge voice id (e.g. en-US-JennyNeural)",
            "tts_voice": "str | None — alias for edge_voice",
            "kokoro_voice": "str | None — explicit Kokoro voice id",
        }

    @property
    def tags(self) -> list[str]:
        return ["audio", "voice_synth"]

    def execute(self, **kwargs) -> Any:
        character_name = kwargs.get("character_name", "A")
        dialogue = kwargs.get("dialogue", "")
        output_path = kwargs.get("output_path", "")
        reference_audio_path = kwargs.get("reference_audio_path")
        emotion = kwargs.get("emotion", "neutral")
        gender = kwargs.get("gender")
        edge_voice = kwargs.get("edge_voice") or kwargs.get("tts_voice")
        kokoro_voice = kwargs.get("kokoro_voice")

        if os.path.dirname(output_path):
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

        if reference_audio_path and os.path.exists(reference_audio_path):
            try:
                return _synthesize_with_cosyvoice(dialogue, reference_audio_path, output_path, emotion)
            except Exception as e:
                print(f"[VoiceSynth] CosyVoice2 failed: {e}. Trying edge-tts...")

        try:
            return _synthesize_with_edge_tts(
                dialogue,
                output_path,
                character_name,
                emotion,
                gender=gender,
                edge_voice=edge_voice,
            )
        except Exception as e:
            print(f"[VoiceSynth] edge-tts failed: {e}. Trying Kokoro...")

        try:
            return _synthesize_with_kokoro(
                dialogue,
                output_path,
                character_name,
                emotion,
                gender=gender,
                kokoro_voice=kokoro_voice,
            )
        except Exception as e:
            print(f"[VoiceSynth] Kokoro failed: {e}. Using tone fallback...")

        return _synthesize_tone_wav(dialogue, output_path)
