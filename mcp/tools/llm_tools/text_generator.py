from typing import Any, Dict
from mcp.base_tool import BaseTool

class TextGeneratorTool(BaseTool):
    @property
    def name(self) -> str:
        return "generate_script_segment"

    @property
    def description(self) -> str:
        return "Generates a structured script segment based on a prompt."

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "prompt": "str — The creative prompt to base the script on",
            "num_scenes": "int — Number of scenes to generate",
        }

    @property
    def tags(self) -> list[str]:
        return ["llm", "text_gen", "creative"]

    def execute(self, **kwargs) -> Any:
        prompt = kwargs.get("prompt", "")
        num_scenes = kwargs.get("num_scenes", 5)
        return f"Generated script for: {prompt} with {num_scenes} scenes."
