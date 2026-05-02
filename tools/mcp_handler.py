"""
MCP Handler — tools/mcp_handler.py
Registers all Phase 2 real model wrappers as dynamically discoverable MCP tools
while preserving Phase 1 backward-compatible MCPToolRegistry.

Two registries exist side by side:
  - mcp_registry  (MCPToolRegistry) — used by Phase 1 agents (backward compat)
  - registry      (MCPRegistry)     — new Phase 2 formal registry (Section 7 guide)
"""

import inspect
import math
import os
import shutil
import struct
import wave
from io import BytesIO
from typing import Any, Callable, Dict, List

from memory.memory_manager import memory_manager

# ──────────────────────────────────────────────────────────────────────────────
# Phase 1 backward-compatible registry (keep unchanged)
# ──────────────────────────────────────────────────────────────────────────────

class MCPToolRegistry:
    """
    Legacy registry used by Phase 1 agents.
    Agents query this registry at runtime to discover and invoke tools.
    """

    def __init__(self):
        self._tools: Dict[str, Callable] = {}

    def register_tool(self, name: str, func: Callable):
        self._tools[name] = func

    def get_available_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": name,
                "description": func.__doc__,
                "parameters": str(inspect.signature(func)),
            }
            for name, func in self._tools.items()
        ]

    def call_tool(self, name: str, **kwargs) -> Any:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not found in MCP registry.")
        return self._tools[name](**kwargs)


# Singleton — Phase 1
mcp_registry = MCPToolRegistry()


# ──────────────────────────────────────────────────────────────────────────────
# Phase 1 tool implementations (unchanged)
# ──────────────────────────────────────────────────────────────────────────────

def generate_script_segment(prompt: str, num_scenes: int = 5):
    """Generates a structured script segment based on a prompt."""
    return f"Generated script for: {prompt} with {num_scenes} scenes."


def commit_memory(key: str, data: Any):
    """Commits character or script metadata to the persistent memory layer."""
    try:
        if key.startswith("char_"):
            description = data.get("appearance", "Character entry")
            traits = {
                "name": data.get("name"),
                "personality": data.get("personality"),
                "reference_style": data.get("reference_style"),
                "image_path": data.get("image_path"),
            }
            memory_manager.store_character(
                character_name=key.replace("char_", ""),
                description=description,
                traits=traits,
            )
        else:
            memory_manager.store_script(
                script_id=key, content=str(data), metadata={"source": "workflow"}
            )
        return {"ok": True, "key": key}
    except Exception as exc:
        return {"ok": False, "key": key, "error": str(exc)}


def query_stock_footage(description: str):
    """Queries reference visual styles or footage for character design."""
    return {
        "description": description,
        "references": [
            "Cyberpunk rain-lit alleys",
            "Noir portrait lighting",
            "High-contrast rooftop skyline",
        ],
    }


def get_task_graph_legacy(scenes: List[Dict[str, Any]]):
    """Builds a scene-level task graph for parallel processing (Phase 1 version)."""
    graph = []
    for scene in scenes:
        sid = int(scene.get("scene_id", 0))
        graph.append(
            {
                "task_id": f"task_scene_{sid:02d}",
                "scene_id": sid,
                "stages": ["voice", "video", "face_swap", "lip_sync"],
                "parallelizable": True,
            }
        )
    return graph


def _write_tone_wav(output_path: str, text: str):
    framerate = 22050
    duration = max(1.5, min(8.0, len(text) / 18.0))
    freq = 200 + (len(text) % 180)
    amplitude = 12000
    n_samples = int(duration * framerate)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with wave.open(output_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        for i in range(n_samples):
            val = int(amplitude * math.sin(2 * math.pi * freq * (i / framerate)))
            wf.writeframesraw(struct.pack("<h", val))
    return duration


def voice_cloning_synthesizer_legacy(text: str, output_path: str, speaker_hint: str = "default"):
    """Generates speech waveform from dialogue text (Phase 1 fallback)."""
    hf_token = os.getenv("HF_API_TOKEN", "").strip()
    if hf_token:
        try:
            import requests
            model = os.getenv("HF_TTS_MODEL", "facebook/mms-tts-eng")
            url = f"https://api-inference.huggingface.co/models/{model}"
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {hf_token}"},
                json={"inputs": text},
                timeout=60,
            )
            if resp.status_code == 200 and resp.content:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                return {"audio_path": output_path, "duration_sec": 0.0, "engine": f"hf:{model}"}
        except Exception:
            pass

    duration = _write_tone_wav(output_path, text)
    return {"audio_path": output_path, "duration_sec": duration, "engine": "local_fallback_tone"}


def identity_validator_legacy(scene: Dict[str, Any]):
    """Validates character identity presence before face mapping (Phase 1 version)."""
    chars = scene.get("characters", [])
    valid = isinstance(chars, list) and len(chars) > 0
    return {"valid": valid, "characters": chars}


def face_swapper_legacy(source_video: str, output_video: str, scene: Dict[str, Any]):
    """Maps character identities over generated scene video (Phase 1 placeholder)."""
    os.makedirs(os.path.dirname(output_video), exist_ok=True)
    shutil.copyfile(source_video, output_video)
    return {"video_path": output_video, "scene_id": scene.get("scene_id")}


def lip_sync_aligner_legacy(input_video: str, input_audio: str, output_video: str):
    """Aligns facial motion to speech timing (Phase 1 placeholder)."""
    os.makedirs(os.path.dirname(output_video), exist_ok=True)
    shutil.copyfile(input_video, output_video)
    return {"video_path": output_video, "audio_path": input_audio, "aligned": True}


def generate_character_image(prompt: str, output_path: str):
    """Generates a character portrait image from a prompt."""
    existing_valid = os.path.exists(output_path) and os.path.getsize(output_path) >= 120000

    try:
        import requests
        import urllib.parse
        from PIL import Image

        seeds = [42, 77, 123]
        for seed in seeds:
            url = (
                "https://image.pollinations.ai/prompt/"
                f"{urllib.parse.quote(prompt)}"
                f"?width=768&height=768&seed={seed}&model=flux"
            )
            resp = requests.get(url, timeout=25)
            if resp.status_code == 200 and resp.content:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                img = Image.open(BytesIO(resp.content)).convert("RGB")
                img.save(output_path, format="PNG")
                size = os.path.getsize(output_path)
                if size >= 120000:
                    return {
                        "ok": True,
                        "image_path": output_path,
                        "engine": f"pollinations:flux(seed={seed})",
                        "size_bytes": size,
                    }
            elif resp.status_code == 429:
                if existing_valid:
                    return {
                        "ok": True,
                        "image_path": output_path,
                        "engine": "kept_existing_image(rate_limited)",
                        "size_bytes": os.path.getsize(output_path),
                    }
    except Exception:
        pass

    hf_token = os.getenv("HF_API_TOKEN", "").strip()
    model = os.getenv("HF_IMAGE_MODEL", "stabilityai/stable-diffusion-2-1")
    if hf_token:
        try:
            import requests
            url = f"https://api-inference.huggingface.co/models/{model}"
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {hf_token}"},
                json={"inputs": prompt},
                timeout=40,
            )
            if resp.status_code == 200 and resp.content:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                try:
                    from PIL import Image
                    img = Image.open(BytesIO(resp.content)).convert("RGB")
                    img.save(output_path, format="PNG")
                except Exception:
                    with open(output_path, "wb") as f:
                        f.write(resp.content)
                return {
                    "ok": True,
                    "image_path": output_path,
                    "engine": f"hf:{model}",
                    "size_bytes": os.path.getsize(output_path),
                }
        except Exception:
            pass

    if existing_valid:
        return {
            "ok": True,
            "image_path": output_path,
            "engine": "kept_existing_image(fallback_avoided)",
            "size_bytes": os.path.getsize(output_path),
        }

    try:
        from PIL import Image, ImageDraw
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img = Image.new("RGB", (768, 768), color=(18, 25, 44))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, 768, 128), fill=(34, 48, 82))
        draw.text((28, 42), "Character Portrait", fill=(245, 248, 255))
        draw.text((28, 86), prompt[:65], fill=(175, 210, 255))
        draw.ellipse((245, 170, 525, 450), fill=(96, 126, 176))
        draw.rectangle((300, 430, 470, 695), fill=(84, 114, 166))
        img.save(output_path, format="PNG")
        return {
            "ok": True,
            "image_path": output_path,
            "engine": "local_stylized_fallback",
            "size_bytes": os.path.getsize(output_path),
        }
    except Exception as exc:
        return {"ok": False, "image_path": output_path, "error": str(exc)}


# Register Phase 1 tools into legacy registry
mcp_registry.register_tool("generate_script_segment", generate_script_segment)
mcp_registry.register_tool("commit_memory", commit_memory)
mcp_registry.register_tool("query_stock_footage", query_stock_footage)
mcp_registry.register_tool("get_task_graph", get_task_graph_legacy)
mcp_registry.register_tool("voice_cloning_synthesizer", voice_cloning_synthesizer_legacy)
mcp_registry.register_tool("identity_validator", identity_validator_legacy)
mcp_registry.register_tool("face_swapper", face_swapper_legacy)
mcp_registry.register_tool("lip_sync_aligner", lip_sync_aligner_legacy)
mcp_registry.register_tool("generate_character_image", generate_character_image)


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2 — register real model wrappers into the new formal MCPRegistry
# ──────────────────────────────────────────────────────────────────────────────

def register_all_tools():
    """
    Register all Phase 2 MCP tools at startup.
    Agents call registry.discover() to find tools at runtime.
    Call this once before invoking any Phase 2 worker.
    """
    from tools.mcp_registry import registry, MCPTool
    from tools.task_graph import get_task_graph
    from models.voice_synth import synthesize_voice
    from models.video_gen import generate_scene_video
    from models.face_swap import swap_face_in_video, validate_identity
    from models.lip_sync import align_lip_sync

    registry.register(MCPTool(
        name="get_task_graph",
        description="Decomposes scene_manifest.json into parallelizable scene tasks.",
        input_schema={
            "manifest_path": "str — path to scene_manifest.json",
            "parallel": "bool — whether to enable parallel branching (default True)",
        },
        handler=get_task_graph,
        tags=["planning", "scene_parser"],
    ))

    registry.register(MCPTool(
        name="voice_cloning_synthesizer",
        description=(
            "Synthesizes dialogue speech using CosyVoice2 voice cloning (primary), "
            "Kokoro TTS (fallback), or local tone WAV (always available)."
        ),
        input_schema={
            "character_name": "str — character identifier",
            "dialogue": "str — line of dialogue to synthesize",
            "output_path": "str — path to save output WAV",
            "reference_audio_path": "str | None — optional 3-10s voice reference WAV",
            "emotion": "str — neutral | happy | sad | angry | fearful",
        },
        handler=synthesize_voice,
        tags=["audio", "voice_synth"],
    ))

    registry.register(MCPTool(
        name="generate_scene_video",
        description=(
            "Generates a video clip from a scene description and character image. "
            "Uses LTX-Video (GPU), Wan2.1 API, or Ken Burns animated zoom (CPU fallback)."
        ),
        input_schema={
            "scene_id": "int — scene number",
            "scene_prompt": "str — visual description of the scene",
            "character_image_path": "str | None — path to character portrait PNG",
            "output_path": "str — path to save output MP4",
            "use_wan": "bool — use Wan2.1 API instead of LTX-Video (default False)",
        },
        handler=generate_scene_video,
        tags=["video", "video_gen"],
    ))

    registry.register(MCPTool(
        name="face_swapper",
        description=(
            "Maps character face from reference image onto all faces in target video "
            "frame by frame using InsightFace inswapper_128."
        ),
        input_schema={
            "source_face_image": "str — path to character portrait PNG",
            "target_video": "str — path to generated scene video",
            "output_path": "str — path to save face-swapped MP4",
        },
        handler=swap_face_in_video,
        tags=["video", "face_swap"],
    ))

    registry.register(MCPTool(
        name="identity_validator",
        description="Validates that a face is detectable in a character reference image.",
        input_schema={
            "image_path": "str — path to character portrait PNG",
        },
        handler=validate_identity,
        tags=["validation", "face_swap"],
    ))

    registry.register(MCPTool(
        name="lip_sync_aligner",
        description=(
            "Synchronizes audio waveform with facial movements. "
            "Uses LatentSync (high quality) or Wav2Lip, with copy fallback."
        ),
        input_schema={
            "video_path": "str — face-swapped video MP4",
            "audio_path": "str — synthesized dialogue WAV",
            "output_path": "str — final lip-synced MP4 path",
            "use_latentsync": "bool — use LatentSync instead of Wav2Lip (default False)",
        },
        handler=align_lip_sync,
        tags=["audio", "video", "lip_sync"],
    ))

    print(f"[MCP] Phase 2: {len(registry.discover())} tools registered successfully.")
    print(f"[MCP] Tool names: {registry.list_tools()}")
