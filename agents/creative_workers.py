from schema.state import MontageState, Character
from tools.mcp_handler import mcp_registry
from memory.memory_manager import memory_manager
import re

class CharacterDesigner:
    """
    Extracts and formalizes character identities from the scenes.
    Ensures identity consistency across scripts.
    """
    def process(self, state: MontageState) -> MontageState:
        print(f"--- [Character Designer] Extracting character identities ---")
        scenes = state.get("scenes", [])
        unique_names = set()
        for scene in scenes:
            unique_names.update(scene.characters)
            
        characters = []
        for name in unique_names:
            # Check memory first for consistency
            # memory_res = memory_manager.query_characters(name)

            profile = self._character_profile(name)
            char = Character(
                name=name,
                personality=profile["personality"],
                appearance=profile["appearance"],
                reference_style=profile["style"],
            )
            characters.append(char)
            
            # Commit to memory via MCP (as per constraint)
            mcp_registry.call_tool("commit_memory", key=f"char_{name}", data=char.dict())
            
        state["characters"] = characters
        state["current_agent"] = "CharacterDesigner"
        return state

    def _character_profile(self, name: str):
        lowered = name.lower()
        if "sora" in lowered:
            return {
                "personality": "Warm, charismatic, and emotionally perceptive",
                "appearance": "Young woman with elegant features, soft expressive eyes, shoulder-length dark hair with subtle cyan highlights, stylish futuristic jacket with luminous accents",
                "style": "Vibrant Neo-Cinematic",
            }
        if "kael" in lowered:
            return {
                "personality": "Calm, clever, and optimistic under pressure",
                "appearance": "Young man with clean modern haircut, confident smile, tailored techwear coat with teal accents and minimal accessories",
                "style": "Vibrant Neo-Cinematic",
            }
        return {
            "personality": "Serene digital guardian with subtle mystery",
            "appearance": "Androgynous holographic entity with translucent contours, luminous amber-cyan patterns, and graceful silhouette",
            "style": "Stylized Holographic Futurism",
        }

class ImageSynthesizer:
    """
    Coordinates visual generation via MCP-discovered tools.
    """
    def synthesize(self, state: MontageState) -> MontageState:
        print(f"--- [Image Synthesizer] Generating character visuals ---")
        characters = state.get("characters", [])
        
        for char in characters:
            # Discover and call image tool via MCP
            print(f"Requesting synthetic image for: {char.name}")
            safe_name = re.sub(r"[^a-z0-9]+", "_", char.name.lower()).strip("_")
            image_path = f"output/image_assets/{safe_name}.png"
            base_prompt = (
                f"Beautiful cinematic character portrait of {char.name}, "
                f"{char.appearance}, personality: {char.personality}, style: {char.reference_style}. "
                "Vibrant but elegant color palette, fashion-forward design, "
                "friendly expression, premium concept art, soft cinematic lighting, "
                "high detail, ultra sharp, 4k, no violence, no battle gear, no weapons."
            )
            result = mcp_registry.call_tool(
                "generate_character_image",
                prompt=base_prompt,
                output_path=image_path,
            )

            # Retry once with stronger style prompt if first result fell back.
            engine = str(result.get("engine", ""))
            if "local_stylized_fallback" in engine:
                retry_prompt = (
                    f"Masterpiece portrait of {char.name}, "
                    f"{char.appearance}, style {char.reference_style}. "
                    "Highly attractive, polished facial features, realistic skin texture, "
                    "colorful editorial fashion lighting, vibrant cyan, magenta, and gold highlights, "
                    "cinematic quality, ultra detailed digital art, no violence, no weapons."
                )
                retry_result = mcp_registry.call_tool(
                    "generate_character_image",
                    prompt=retry_prompt,
                    output_path=image_path,
                )
                if retry_result.get("ok"):
                    result = retry_result

            print(f" -> engine: {result.get('engine', 'unknown')}, file: {result.get('image_path')}")
            char.image_path = result.get("image_path", image_path)
            
        state["current_agent"] = "ImageSynthesizer"
        state["status"] = "completed"
        return state

def character_node(state: MontageState):
    return CharacterDesigner().process(state)

def image_node(state: MontageState):
    return ImageSynthesizer().synthesize(state)
