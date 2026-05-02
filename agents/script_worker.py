from schema.state import MontageState, Scene, Character
from tools.mcp_handler import mcp_registry
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import HumanMessage
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

import json

system_prompt = """You are a screenplay generation agent.
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
Generate at least 3 coherent scenes with cinematic visual cues."""

class ScriptwriterAgent:
    """
    Transforms abstract prompts into structured scripts.
    Fulfills the reasoning loop: Decomposition -> Expansion -> Visual Cue Injection.
    """
    def __init__(self, model_name: str = "gemini-1.5-flash"):
        if HAS_GENAI:
            try:
                self.llm = ChatGoogleGenerativeAI(model=model_name)
            except Exception:
                self.llm = None
        else:
            self.llm = None

    def generate(self, state: MontageState) -> MontageState:
        print(f"--- [Scriptwriter] Generating script autonomously ---")
        prompt = state.get("user_prompt", "")
        
        # Reason 1: Decomposition & Discovery
        # In a real scenario, we'd query MCP for available generation tools
        tools = mcp_registry.get_available_tools()
        print(f"discovered tools: {[t['name'] for t in tools]}")
        
        # Reason 2: Expansion (LLM Call or deterministic fallback)
        if self.llm:
            try:
                response = self.llm.invoke([
                    HumanMessage(content=f"{system_prompt}\n\nUser Prompt: {prompt}")
                ])
                llm_text = response.content
                state["raw_script"] = llm_text
                parsed = self._parse_scene_payload(llm_text)
                if parsed:
                    state["scenes"] = parsed
                else:
                    state["scenes"] = self._fallback_scenes(prompt)
            except Exception as e:
                print(f"LLM Invoke failed: {e}. Using mock fallback.")
                state["scenes"] = self._fallback_scenes(prompt)
                state["raw_script"] = self._scenes_to_raw_script(state["scenes"])
        else:
            state["scenes"] = self._fallback_scenes(prompt)
            state["raw_script"] = self._scenes_to_raw_script(state["scenes"])
        
        state["status"] = "generating"
        state["current_agent"] = "Scriptwriter"
        return state

    def _parse_scene_payload(self, raw_text: str):
        try:
            payload = json.loads(raw_text)
            scenes = payload.get("scenes", [])
            normalized = []
            for scene in scenes:
                normalized.append(
                    Scene(
                        scene_id=int(scene["scene_id"]),
                        location=scene["location"],
                        characters=list(scene["characters"]),
                        dialogue=list(scene["dialogue"])
                    )
                )
            return normalized if normalized else None
        except Exception:
            return None

    def _fallback_scenes(self, prompt: str):
        topic = (prompt or "A hopeful futuristic journey through a luminous smart city").strip()
        return [
            Scene(
                scene_id=1,
                location="EXT. SKYBRIDGE GARDEN DISTRICT - NEON EVENING",
                characters=["Kael", "Sora"],
                dialogue=[
                    {"speaker": "Kael", "line": f"Tonight we make this city feel alive again. {topic}", "visual_cue": "Vibrant cyan, pink, and gold reflections across wet glass walkways, elegant cinematic glow"},
                    {"speaker": "Sora", "line": "Then let's make every frame unforgettable.", "visual_cue": "Close-up with radiant magenta rim light, soft bloom, warm smile, premium fashion look"}
                ]
            ),
            Scene(
                scene_id=2,
                location="INT. AURORA ARCHIVE ATRIUM - NIGHT",
                characters=["Kael", "Sora", "Warden AI"],
                dialogue=[
                    {"speaker": "Warden AI", "line": "Creative access granted. Curating visual symphony.", "visual_cue": "Floating holographic petals in amber and cyan, mirrored marble floor, elegant light trails"},
                    {"speaker": "Sora", "line": "Perfect. Let's turn memory into color and music.", "visual_cue": "Low-angle fashion portrait, vibrant teal-gold split lighting, airy cinematic haze"}
                ]
            ),
            Scene(
                scene_id=3,
                location="EXT. PANORAMIC ROOFTOP STAGE - GOLDEN BLUE DAWN",
                characters=["Kael", "Sora"],
                dialogue=[
                    {"speaker": "Kael", "line": "The real prize was giving everyone a brighter story.", "visual_cue": "Radiant dawn gradient of cobalt and gold, crisp silhouettes, cinematic lens flares, celebratory mood"},
                    {"speaker": "Sora", "line": "And now the whole skyline feels like a heartbeat.", "visual_cue": "Wide anamorphic frame, vivid warm highlights, gentle cool shadows, uplifting atmosphere"}
                ]
            )
        ]

    def _scenes_to_raw_script(self, scenes):
        lines = []
        for scene in scenes:
            lines.append(scene.location)
            lines.append("[Cinematic action beat and staging]")
            for turn in scene.dialogue:
                lines.append(f"{turn['speaker'].upper()}: {turn['line']}")
            lines.append("")
        return "\n".join(lines).strip()

def scriptwriter_node(state: MontageState):
    return ScriptwriterAgent().generate(state)
