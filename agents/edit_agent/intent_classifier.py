"""
Edit Agent — Intent Classifier
LLM-powered agent that parses natural language edit queries into structured intent objects.
"""

import logging
from typing import Dict, Any, Optional
from shared.schemas.state import MontageState
from shared.utils.llm_client import chat_json

logger = logging.getLogger("IntentClassifier")

INTENT_SYSTEM_PROMPT = """
You are an Intelligent Edit Agent for a film production pipeline.
Your goal is to parse natural language instructions into a structured JSON "Intent Object".

TARGET CATEGORIES:
1. "audio" — Targets TTS content (change what is said) or character voice identity.
2. "audio_fx" — Targets fine-grained audio properties (pitch, speed, volume, filters like radio/reverb) on EXISTING audio.
3. "video_frame" — Targets visual prompts or still image generation for one or more scenes (change what is in the scene).
4. "video_fx" — Targets fine-grained visual properties (brightness, contrast, saturation, sepia, grayscale) on EXISTING video.
5. "video" — Targets the full compositing step (subtitles, transitions, global BGM). Use for "change background music", "more upbeat score", "remove music", "quieter bed", "different BGM mood".
6. "script" — Targets the story/script output. Requires re-running Phase 1.

JSON SCHEMA:
{
  "intent": "string (e.g., pitch_shift, adjust_brightness, change_voice_tone, add_bgm, etc.)",
  "target": "audio | audio_fx | video_frame | video_fx | video | script",
  "scope": "string (e.g., 'scene:1', 'character:Alex', 'global')",
  "parameters": {
    "pitch": "float (0.5 to 1.5)",
    "brightness": "float (-1.0 to 1.0)",
    "contrast": "float (0.0 to 2.0)",
    "filter_type": "radio | telephone | reverb | grayscale | sepia | vignette",
    "speed": "float (0.5 to 2.0)",
    "any_other_key": "any_value"
  },
  "explanation": "Brief reasoning for this classification"
}

ROUTING RULES:
- Deeper/higher pitch on existing dialogue without changing words: prefer "audio_fx" + parameters.pitch (0.5–1.0 = deeper, 1.0+ = higher), scope "character:{Name}" if a name is given, else "global".
- Changing voice identity (gender, accent, different neural voice) or re-synthesizing after script tweaks: use "audio" + scope "character:{Name}". When the user says "change to a man/male voice" or "change to a woman/female voice", include parameters.gender ("male" or "female"). Do NOT include parameters.pitch unless the user explicitly asked for deeper/higher pitch; the gender field already routes TTS to the correct voice pool.
- Background music / score / underscore / "more upbeat" / "different mood music" / "remove BGM": use target "video" with parameters.mood in happy|sad|tense|calm|epic|neutral and optional parameters.bgm_style as a short natural-language hint for music search.
- If the user ONLY wants background music changed (no subtitle, transition, or scene edits), set parameters.remix_bgm_only to true. If they explicitly need a full re-composite (e.g. re-burn subtitles or re-merge after scene swaps), set parameters.full_composite to true.

EXAMPLES:
- "Make Alex's voice deeper" -> {"intent": "pitch_shift", "target": "audio_fx", "scope": "character:Alex", "parameters": {"pitch": 0.8}}
- "Make his voice sound like it's over a radio" -> {"intent": "apply_filter", "target": "audio_fx", "scope": "character:Alex", "parameters": {"filter_type": "radio"}}
- "Make the first scene a bit darker" -> {"intent": "adjust_brightness", "target": "video_fx", "scope": "scene:1", "parameters": {"brightness": -0.2}}
- "Turn the whole video black and white" -> {"intent": "apply_filter", "target": "video_fx", "scope": "global", "parameters": {"filter_type": "grayscale"}}
- "Change Alex's line to 'Hello there'" -> {"intent": "change_dialogue", "target": "audio", "scope": "character:Alex", "parameters": {"text": "Hello there"}}
- "Change the comedian's voice to a man" -> {"intent": "change_voice_gender", "target": "audio", "scope": "character:Comedian", "parameters": {"gender": "male"}}
- "Make Sarah sound female" -> {"intent": "change_voice_gender", "target": "audio", "scope": "character:Sarah", "parameters": {"gender": "female"}}
- "Use more upbeat background music" -> {"intent": "adjust_bgm", "target": "video", "scope": "global", "parameters": {"mood": "happy", "bgm_style": "bright upbeat energetic instrumental", "remix_bgm_only": true}}
- "Make the score sadder / melancholic" -> {"intent": "adjust_bgm", "target": "video", "scope": "global", "parameters": {"mood": "sad", "bgm_style": "melancholy emotional piano"}}
- "Remove background music" -> {"intent": "remove_bgm", "target": "video", "scope": "global", "parameters": {"apply_bgm": false}}

Return ONLY the JSON object.
"""

def classify_edit_intent(user_query: str, state_summary: Optional[str] = None) -> Dict[str, Any]:
    """
    Invokes the LLM to classify the user's edit intent.
    """
    logger.info(f"🔍 [IntentClassifier] Classifying: {user_query}")
    
    user_prompt = f"User Instruction: {user_query}"
    if state_summary:
        user_prompt += f"\n\nCurrent Project Context: {state_summary}"
        
    try:
        intent_obj = chat_json(system=INTENT_SYSTEM_PROMPT, user=user_prompt, temperature=0.2)
        logger.info(f"✅ [IntentClassifier] Parsed Intent: {intent_obj.get('intent')} on {intent_obj.get('target')}")
        return intent_obj
    except Exception as e:
        logger.error(f"❌ [IntentClassifier] Failed to parse intent: {e}")
        return {
            "intent": "unknown",
            "target": "unknown",
            "scope": "global",
            "parameters": {},
            "error": str(e)
        }

def route_input(state: MontageState) -> str:
    """
    Legacy routing function to select between Manual Script Upload or Auto Generation.
    Returns 'validator' for manual mode, 'scriptwriter' for auto mode.
    """
    if state.get("input_mode") == "manual":
        return "validator"
    return "scriptwriter"
