"""
Story Agent — agent.py
Combines ScriptwriterAgent (script generation) and CharacterDesigner / ImageSynthesizer
(character design and image generation) from the old script_worker.py and creative_workers.py.

LangGraph node functions exported:
    scriptwriter_node(state) -> MontageState
    character_node(state)    -> MontageState
    image_node(state)        -> MontageState
"""

import hashlib
import json
import re
import os
import time
import logging
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("StoryAgent")

from shared.schemas.state import MontageState, Scene, Character
from mcp.tool_registry import registry as mcp_registry
from agents.story_agent.planner import fallback_scenes, scenes_to_raw_script

try:
    from langchain_core.messages import HumanMessage
except ImportError:
    HumanMessage = None  # type: ignore[misc, assignment]

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

try:
    from langchain_groq import ChatGroq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False


# ─────────────────────────────────────────────────────────────────────────────
# Scriptwriter Agent
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a screenplay generation agent.
Return ONLY valid JSON with this schema:
{
  "scenes": [
    {
      "scene_id": 1,
      "location": "string",
      "characters": ["Name1", "Name2"],
      "dialogue": [
        {
          "speaker": "Name1",
          "line": "string",
          "visual_cue": "string"
        }
      ]
    }
  ]
}
Generate at least {number_of_scenes} coherent scenes with cinematic visual cues."""


class ScriptwriterAgent:
    """
    Transforms abstract prompts into structured scripts.
    Fulfils the reasoning loop: Decomposition -> Expansion -> Visual Cue Injection.
    """

    def __init__(self, model_name: str = "gemini-pro"):
        self.model_name = model_name
        if HAS_GENAI:
            try:
                self.llm = ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=os.environ.get("GEMINI_API_KEY")
                )
            except Exception as e:
                logger.error(f"❌ [ScriptwriterAgent] Failed to initialize Gemini LLM: {e}")
                self.llm = None
        else:
            self.llm = None

    def generate(self, state: MontageState) -> MontageState:
        logger.info("🎬 [Scriptwriter] Started autonomous script generation...")
        prompt = state.get("user_prompt", "")
        num_scenes = os.environ.get("NUMBER_OF_SCENES", "3")

        # Reason 1: Decomposition & Discovery
        tools = mcp_registry.get_available_tools()
        print(f"discovered tools: {[t['name'] for t in tools]}")

        # Reason 2: Expansion (LLM call or deterministic fallback)
        llm_text = None
        
        if self.llm and HumanMessage is not None:
            try:
                sys_prompt = _SYSTEM_PROMPT.replace("{number_of_scenes}", str(num_scenes))
                response = self.llm.invoke(
                    [HumanMessage(content=f"{sys_prompt}\n\nUser Prompt: {prompt}")]
                )
                llm_text = response.content
                logger.info("✅ [Scriptwriter] Successfully generated script via Gemini.")
            except Exception as e:
                logger.warning(f"⚠️ [Scriptwriter] Gemini Invoke failed: {e}. Attempting Groq fallback...")
        
        # Groq Fallback
        if not llm_text and HAS_GROQ and os.environ.get("GROQ_API_KEY") and HumanMessage is not None:
            try:
                groq_llm = ChatGroq(
                    model_name="llama-3.1-8b-instant",
                    groq_api_key=os.environ.get("GROQ_API_KEY")
                )
                sys_prompt = _SYSTEM_PROMPT.replace("{number_of_scenes}", str(num_scenes))
                response = groq_llm.invoke(
                    [HumanMessage(content=f"{sys_prompt}\n\nUser Prompt: {prompt}")]
                )
                llm_text = response.content
                logger.info("✅ [Scriptwriter] Successfully generated script via Groq fallback.")
            except Exception as e2:
                logger.error(f"❌ [Scriptwriter] Groq Invoke failed: {e2}. Forcing deterministic fallback.")
                
        if llm_text:
            try:
                state["raw_script"] = llm_text
                parsed = self._parse_scene_payload(llm_text)
                state["scenes"] = parsed if parsed else fallback_scenes(prompt)
            except Exception as parse_e:
                logger.error(f"❌ [Scriptwriter] Failed to parse generated JSON script: {parse_e}")
                state["scenes"] = fallback_scenes(prompt)
                state["raw_script"] = scenes_to_raw_script(state["scenes"])
        else:
            state["scenes"] = fallback_scenes(prompt)
            state["raw_script"] = scenes_to_raw_script(state["scenes"])

        state["status"] = "generating"
        state["current_agent"] = "Scriptwriter"
        return state

    def _parse_scene_payload(self, raw_text: str):
        try:
            # Clean markdown formatting and find JSON bounds
            cleaned_text = raw_text.strip()
            start_idx = cleaned_text.find("{")
            end_idx = cleaned_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                cleaned_text = cleaned_text[start_idx:end_idx+1]
            
            # Remove potential internal markdown lines that might have survived
            cleaned_text = "\n".join([line for line in cleaned_text.split("\n") if "```" not in line]).strip()
            
            try:
                payload = json.loads(cleaned_text)
            except json.JSONDecodeError:
                # Basic "repair" attempt: fix trailing commas in lists/objects
                import re
                cleaned_text = re.sub(r",\s*([\]}])", r"\1", cleaned_text)
                payload = json.loads(cleaned_text)
            scenes = payload.get("scenes", [])
            normalized = [
                Scene(
                    scene_id=int(s["scene_id"]),
                    location=s["location"],
                    characters=list(s["characters"]),
                    dialogue=list(s["dialogue"]),
                )
                for s in scenes
            ]
            return normalized if normalized else None
        except Exception as e:
            logger.error(f"❌ [Scriptwriter] JSON Parsing Error: {e}")
            return None


def _stable_bucket(name: str, modulus: int) -> int:
    h = hashlib.md5(name.strip().encode("utf-8")).hexdigest()
    return int(h[:12], 16) % modulus


def _scene_context_for_character(name: str, scenes: List[Scene]) -> str:
    """Collect locations, dialogue, and visual cues involving this character."""
    chunks: List[str] = []
    for scene in scenes:
        if name not in scene.characters:
            continue
        chunks.append(f"Scene {scene.scene_id} — {scene.location}")
        for turn in scene.dialogue:
            sp = str(turn.get("speaker", "")).strip()
            line = str(turn.get("line", "")).strip()
            vc = str(turn.get("visual_cue", "")).strip()
            if sp == name:
                bits = [f'{name}: "{line}"']
                if vc:
                    bits.append(f"(visual: {vc})")
                chunks.append("  " + " ".join(bits))
            elif sp and line:
                chunks.append(f'  {sp}: "{line}"')
    text = "\n".join(chunks).strip()
    return text[:6000] if len(text) > 6000 else text


def _is_weak_appearance(text: Optional[str]) -> bool:
    if not text or not str(text).strip():
        return True
    s = str(text).strip()
    if len(s) < 36:
        return True
    low = s.lower()
    if "distinctive individual named" in low:
        return True
    if "cinematic lighting" in low and len(s) < 120:
        return True
    return False


def _clamp_appearance(text: str, max_chars: int = 280) -> str:
    """Keep appearance short: face, hair, body, clothing, personal accessories only."""
    s = (text or "").strip()
    if len(s) <= max_chars:
        return s
    cut = s[: max_chars - 1].rsplit(" ", 1)[0].strip()
    return cut.rstrip(",;") + "…"


_HEURISTIC_ARCHETYPES: List[tuple] = [
    (
        ("detective", "inspector", "officer", "cop", "lieutenant", "sergeant"),
        {
            "personalities": [
                "Methodical, skeptical, quietly intense; reads people faster than they lie.",
                "Dry wit under pressure; trusts evidence over instinct but follows both.",
                "Patient and relentless; uncomfortable with gray zones yet lives in them.",
                "Controlled empathy; protective of victims, ice-cold toward manipulators.",
            ],
            "appearances": [
                "Early fifties, weathered olive skin, silver-threaded black hair swept back. "
                "Charcoal suit with soft wrinkles at the elbows, narrow black tie, scuffed leather oxfords. "
                "Crow's feet, steady hazel eyes, faint scar along the left jaw.",
                "Mid forties, sharp cheekbones, closely cropped beard with premature gray at the temples. "
                "Navy blazer over an open-collar white shirt, slim wristwatch, tired eyes that still miss nothing.",
                "Late thirties, athletic build, dark hair in a careful side part. "
                "Tan trench worn over a gray sweater, leather messenger bag strap visible; thin silver ring on one hand.",
                "Sixties, gaunt elegance, wire glasses, silver hair in a neat crop. "
                "Brown tweed jacket, knit vest, polished cane hooked on an arm — calm voice mirrored in unhurried posture.",
            ],
            "voices": [
                "Low, measured baritone with a slight rasp; slows down when cornering a contradiction.",
                "Clear mid-range, clipped consonants; drops volume instead of shouting.",
                "Warm tenor that turns steel-flat under stress.",
                "Slow gravel with courtroom patience; every pause feels intentional.",
            ],
            "styles": [
                "Gritty neo-noir palette, warm rim highlights",
                "Cool desaturated procedural tones",
                "High-contrast portrait drama",
                "Muted teal-and-amber thriller palette",
            ],
        },
    ),
    (
        ("suspect", "criminal", "perp", "prisoner", "convict"),
        {
            "personalities": [
                "Smooth deflection and practiced calm; anger flashes when cornered.",
                "Anxious intelligence; talks too much when lying.",
                "Charismatic manipulator who mirrors whoever interrogates them.",
                "Hard-edged survivor; respect earned through nerve, not charm.",
            ],
            "appearances": [
                "Late twenties, athletic, cropped dark hair with a faded surgical scar at the hairline. "
                "Black fitted henley, lightweight jacket with the collar popped, restless hands, restless eyes.",
                "Mid thirties, pale complexion, unkempt blond hair tucked behind one ear. "
                "Layered thrift-store knits, ink peeking at the wrist, a jittery half-smile that never reaches the eyes.",
                "Early forties, broad-shouldered, buzz cut going silver at the sides. "
                "Work boots, dark jeans, plain tee under an open flannel — posture pitched slightly forward, coiled.",
                "Thirties, androgynous features, sharp eyeliner, slicked hair. "
                "Tailored black coat, silver earrings, one chipped tooth visible when they grin — cocky until silence falls.",
            ],
            "voices": [
                "Quick tenor with a tendency to laugh off serious questions.",
                "Soft baritone, overly polite — consonants too precise when stressed.",
                "Nasal mid-tone that rises when challenged.",
                "Hoarse alto; sentences shorten when lying.",
            ],
            "styles": [
                "High-contrast cool-key portrait",
                "Harsh practical-style highlights",
                "Naturalistic muted contrast",
                "Stylized teal-shadow palette",
            ],
        },
    ),
    (
        ("witness", "reporter", "journalist", "bystander"),
        {
            "personalities": [
                "Observant but shaken; detail-oriented when recounting events.",
                "Professional curiosity tempered by fear of reprisal.",
                "Empathic storyteller who lingers on sensory memories.",
            ],
            "appearances": [
                "Early thirties, neat bob haircut, freckled nose. "
                "Olive trench, scarf loosely looped, leather tote — smartphone gripped like an anchor.",
                "Mid twenties, curly hair, wire-rim glasses sliding low on the bridge. "
                "Denim jacket over a band tee, messenger bag heavy with notebooks.",
                "Forties, conservative blazer, sensible heels scuffed at the toe. "
                "Minimal makeup, tired eyes brightening when recalling a crucial detail.",
            ],
            "voices": [
                "Bright soprano that cracks under recall; expressive hands in speech.",
                "Measured alto with broadcast polish fraying at the edges.",
                "Soft-spoken tenor that speeds up when nervous.",
            ],
            "styles": [
                "Natural daylight-balanced portrait",
                "Neutral documentary contrast",
                "Soft wrap portrait light",
            ],
        },
    ),
]


_DEFAULT_HEURISTIC = {
    "personalities": [
        "Grounded and observant; reacts first with caution, then decisive action.",
        "Warm exterior with guarded boundaries; humor hides old wounds.",
        "Idealistic but fraying under pressure; loyalty is their anchor.",
        "Pragmatic streak; uncomfortable with spectacle but rises to it anyway.",
    ],
    "appearances": [
        "Mid thirties, medium-brown skin, natural hair in protective twists pinned up. "
        "Structured wool coat in camel, simple gold hoops, confident stance — expression attentive and composed.",
        "Late twenties, angular face, dark eyes under thick brows. "
        "Layered streetwear: oversized charcoal hoodie, technical vest, clean sneakers; restless energy in the shoulders.",
        "Early forties, laugh lines, salt-and-pepper stubble kept short. "
        "Rolled sleeves on a chambray shirt, vintage wristwatch, ink-black suspenders — relaxed posture, sharp gaze.",
        "Mid twenties, East Asian features, straight black hair with an undercut. "
        "Minimalist black turtleneck, tailored trousers, small silver nose stud — stillness that reads as confidence.",
    ],
    "voices": [
        "Warm mid-register with clear diction; slows down when choosing words carefully.",
        "Bright, slightly nasal alto full of unpredictable cadence.",
        "Deep calm baritone; smiles audible even when the mouth isn't shown.",
        "Breathy tenor that firms into authority when challenged.",
    ],
    "styles": [
        "Contemporary cinematic realism with rich skin tones",
        "Elevated indie drama lighting",
        "Soft volumetric studio portrait",
        "Neo-noir color with restrained saturation",
    ],
}


def _select_heuristic_kit(name: str) -> Dict[str, Any]:
    lower = name.lower()
    for keywords, kit in _HEURISTIC_ARCHETYPES:
        if any(k in lower for k in keywords):
            return kit
    return _DEFAULT_HEURISTIC


def _heuristic_character_profile(name: str) -> Dict[str, str]:
    kit = _select_heuristic_kit(name)
    bp = _stable_bucket(name, 10_007)
    personality = kit["personalities"][bp % len(kit["personalities"])]
    appearance = _clamp_appearance(kit["appearances"][bp % len(kit["appearances"])])
    voice_profile = kit["voices"][bp % len(kit["voices"])]
    reference_style = kit["styles"][bp % len(kit["styles"])]

    return {
        "personality": personality,
        "appearance": appearance.strip(),
        "voice_profile": voice_profile,
        "reference_style": reference_style,
    }


def _extract_json_object(raw: str) -> Optional[str]:
    if not raw:
        return None
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _parse_profile_blob(blob: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        try:
            data = json.loads(re.sub(r",\s*([\]}])", r"\1", blob))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _profile_llm_json(prompt: str) -> Optional[Dict[str, Any]]:
    """Gemini then Groq; returns parsed dict or None."""
    if HumanMessage is None:
        return None
    messages = [HumanMessage(content=prompt.strip())]

    writer = ScriptwriterAgent()
    if writer.llm:
        try:
            raw = writer.llm.invoke(messages).content
            blob = _extract_json_object(raw)
            if blob:
                parsed = _parse_profile_blob(blob)
                if parsed:
                    return parsed
        except Exception as e:
            logger.warning(f"⚠️ [CharacterDesigner] Gemini profile call failed: {e}")

    if HAS_GROQ and os.environ.get("GROQ_API_KEY"):
        try:
            groq_llm = ChatGroq(
                model_name="llama-3.1-8b-instant",
                groq_api_key=os.environ.get("GROQ_API_KEY"),
            )
            raw = groq_llm.invoke(messages).content
            blob = _extract_json_object(raw)
            if blob:
                parsed = _parse_profile_blob(blob)
                if parsed:
                    return parsed
        except Exception as e:
            logger.warning(f"⚠️ [CharacterDesigner] Groq profile call failed: {e}")

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Character Designer
# ─────────────────────────────────────────────────────────────────────────────

class CharacterDesigner:
    """
    Extracts and formalises character identities from the scenes.
    Ensures identity consistency across scripts.
    """

    def process(self, state: MontageState) -> MontageState:
        logger.info("🎭 [Character Designer] Extracting character identities...")
        scenes = state.get("scenes", [])
        unique_names: set = set()
        for scene in scenes:
            unique_names.update(scene.characters)

        characters = []
        for name in sorted(unique_names):
            profile = self._generate_ai_profile(name, state.get("user_prompt", ""), scenes)
            char = Character(
                name=name,
                personality=profile.get("personality", "Mysterious"),
                appearance=profile.get("appearance", "Humanoid"),
                voice_profile=profile.get("voice_profile", "Natural, steady"),
                reference_style=profile.get("reference_style", "Cinematic"),
            )
            characters.append(char)
            mcp_registry.call_tool("commit_memory", key=f"char_{name}", data=char.dict())

        state["characters"] = characters
        state["current_agent"] = "CharacterDesigner"
        return state

    def _generate_ai_profile(self, name: str, user_prompt: str, scenes: List[Scene]) -> dict:
        """LLM-written profile grounded in script context; concrete heuristic fallback if thin or offline."""
        scene_ctx = _scene_context_for_character(name, scenes)
        heuristic = _heuristic_character_profile(name)

        prompt = f"""You are a visual development lead for film.

Character name: {name}

Story brief (for tone only — do NOT paste into appearance):
{user_prompt or "(none)"}

Script involving this character (infer wardrobe consistency only; do NOT describe places or backgrounds in appearance):
{scene_ctx or "(none)"}

Hard rules:
- "appearance": ONE or TWO short sentences ONLY. Describe ONLY the person: apparent age, build, skin, face, hair,
  clothing, jewelry, glasses, scars, posture. NO backgrounds, NO locations, NO props tied to a setting (desks, vehicles,
  buildings), NO weather, NO lighting descriptions, NO plot/scene recap.
- "voice_profile": timbre, pace, accent hints if any — not generic "professional clear balanced".
- "personality": brief specific behavioral traits under pressure.
- "reference_style": short color/mood label for portraits only (no location words).

Return ONLY valid JSON:
{{"personality":"...","appearance":"...","voice_profile":"...","reference_style":"..."}}"""

        parsed = _profile_llm_json(prompt)
        if not parsed:
            logger.warning(f"⚠️ [CharacterDesigner] No LLM profile for {name}; using heuristic appearance.")
            return heuristic

        def _field(key: str) -> str:
            v = parsed.get(key)
            return str(v).strip() if v is not None else ""

        appearance = _clamp_appearance(_field("appearance"))
        if _is_weak_appearance(appearance):
            logger.info(f"[CharacterDesigner] Enriching thin LLM appearance for {name} with heuristic detail.")
            merged = {
                "personality": _field("personality") or heuristic["personality"],
                "appearance": heuristic["appearance"],
                "voice_profile": _field("voice_profile") or heuristic["voice_profile"],
                "reference_style": _field("reference_style") or heuristic["reference_style"],
            }
            for key in ("personality", "voice_profile", "reference_style"):
                if len(merged[key]) < 18:
                    merged[key] = heuristic[key]
            return merged

        out = {
            "personality": _field("personality") or heuristic["personality"],
            "appearance": appearance,
            "voice_profile": _field("voice_profile") or heuristic["voice_profile"],
            "reference_style": _field("reference_style") or heuristic["reference_style"],
        }
        for key in ("personality", "voice_profile", "reference_style"):
            if len(out[key]) < 12:
                out[key] = heuristic[key]
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Image Synthesizer
# ─────────────────────────────────────────────────────────────────────────────

class ImageSynthesizer:
    """
    Coordinates visual generation via MCP-discovered tools.
    """

    def synthesize(self, state: MontageState) -> MontageState:
        logger.info("🖼️ [Image Synthesizer] Generating character visuals...")
        characters = state.get("characters", [])

        synth_max = int(os.environ.get("IMAGE_GEN_SYNTH_MAX_ATTEMPTS", "6"))
        synth_backoff = float(os.environ.get("IMAGE_GEN_SYNTH_BACKOFF_SEC", "22"))

        def _portrait_ok(res: dict) -> bool:
            if not res.get("ok"):
                return False
            eng = str(res.get("engine", ""))
            return "local_stylized_fallback" not in eng

        for char in characters:
            logger.info(f"   -> Requesting synthetic image for: {char.name}")
            safe_name = re.sub(r"[^a-z0-9]+", "_", char.name.lower()).strip("_")
            phase1_dir = os.environ.get("PHASE1_OUTPUT_DIR", "data/outputs/phase1")
            image_path = f"{phase1_dir}/image_assets/{safe_name}.png"

            base_prompt = (
                f"Character portrait, {char.name}. {char.appearance} "
                f"Facial expression reflecting: {char.personality}. "
                f"Color and mood: {char.reference_style}. "
                "Centered head-and-shoulders, clean simple background, no busy environment, "
                "high detail, 4k, no weapons."
            )
            alt_prompt = (
                f"Portrait of {char.name}. {char.appearance} "
                f"Mood: {char.reference_style}. "
                "Polished features, realistic skin, simple neutral background, no weapons."
            )

            result: dict = {}
            for synth_try in range(synth_max):
                prompt = alt_prompt if synth_try % 2 == 1 else base_prompt
                result = mcp_registry.call_tool(
                    "generate_character_image",
                    prompt=prompt,
                    output_path=image_path,
                )
                if _portrait_ok(result):
                    break
                if synth_try < synth_max - 1:
                    delay = min(synth_backoff * (synth_try + 1), 180)
                    logger.warning(
                        "   -> Portrait for %s still failing (%s); sleeping %.0fs then retrying (%s/%s).",
                        char.name,
                        result.get("engine", "unknown"),
                        delay,
                        synth_try + 2,
                        synth_max,
                    )
                    time.sleep(delay)

            logger.info(f"   -> Image generated using {result.get('engine', 'unknown')}")
            final_path = result.get("image_path", image_path)
            char.image_path = final_path

            # Commit the updated character (with image_path) back to persistent storage
            mcp_registry.call_tool("commit_memory", key=f"char_{char.name}", data=char.dict())

        state["current_agent"] = "ImageSynthesizer"
        state["status"] = "completed"
        return state


# ─────────────────────────────────────────────────────────────────────────────
# LangGraph node functions
# ─────────────────────────────────────────────────────────────────────────────

def scriptwriter_node(state: MontageState) -> MontageState:
    return ScriptwriterAgent().generate(state)


def character_node(state: MontageState) -> MontageState:
    return CharacterDesigner().process(state)


def image_node(state: MontageState) -> MontageState:
    return ImageSynthesizer().synthesize(state)
