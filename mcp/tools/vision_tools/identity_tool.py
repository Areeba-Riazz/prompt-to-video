import os
from typing import Any, Dict
from mcp.base_tool import BaseTool

# We rely on the face analyzer loaded in face_swap_tool, but since this might run independently,
# we duplicate the lazy loader or import it if needed. However, since they are in the same python process,
# importing the private loader from face_swap_tool is cleaner.

def _lazy_validate(image_path: str) -> bool:
    from mcp.tools.vision_tools.face_swap_tool import _load_insightface_models, _face_analyzer
    
    if not _load_insightface_models():
        print("[IdentityValidator] Skipping validation (models not available) — assuming valid.")
        return True

    try:
        import cv2  # type: ignore
        img = cv2.imread(image_path)
        if img is None:
            print(f"[IdentityValidator] Cannot read image: {image_path}")
            return False
        faces = _face_analyzer.get(img)
        result = len(faces) > 0
        print(f"[IdentityValidator] Identity validation: {'PASS' if result else 'FAIL'} — {image_path}")
        return result
    except Exception as e:
        print(f"[IdentityValidator] Validation error: {e}")
        return False


class IdentityValidatorTool(BaseTool):
    @property
    def name(self) -> str:
        return "identity_validator"

    @property
    def description(self) -> str:
        return "Validates that a face is detectable in a character reference image."

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "image_path": "str — path to character portrait PNG",
        }

    @property
    def tags(self) -> list[str]:
        return ["validation", "face_swap", "vision"]

    def execute(self, **kwargs) -> Any:
        image_path = kwargs.get("image_path", "")
        return _lazy_validate(image_path)
