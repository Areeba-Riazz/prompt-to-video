import os
import subprocess
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("VideoFXTool")

def video_fx_tool(
    input_path: str,
    output_path: str,
    brightness: Optional[float] = 0.0, # -1.0 to 1.0 (0 is normal)
    contrast: Optional[float] = 1.0,   # 0.0 to 10.0 (1 is normal)
    saturation: Optional[float] = 1.0, # 0.0 to 10.0 (1 is normal)
    gamma: Optional[float] = 1.0,      # 0.1 to 10.0 (1 is normal)
    filter_type: Optional[str] = None # "grayscale", "sepia", "vignette", "blur"
) -> Dict[str, Any]:
    """
    Applies post-production video filters using ffmpeg eq filter and others.
    """
    if not os.path.exists(input_path):
        return {"ok": False, "error": f"Input file not found: {input_path}"}

    vf_filters = []

    # 1. Basic EQ (Brightness, Contrast, Saturation, Gamma)
    # eq filter: contrast:brightness:saturation:gamma
    if any(v != 1.0 and v != 0.0 for v in [brightness, contrast, saturation, gamma]):
        vf_filters.append(f"eq=contrast={contrast}:brightness={brightness}:saturation={saturation}:gamma={gamma}")

    # 2. Presets
    if filter_type == "grayscale":
        vf_filters.append("format=gray")
    elif filter_type == "sepia":
        vf_filters.append("colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131")
    elif filter_type == "vignette":
        vf_filters.append("vignette=PI/4")
    elif filter_type == "blur":
        vf_filters.append("boxblur=5:1")

    filter_str = ",".join(vf_filters) if vf_filters else "copy"
    
    cmd = ["ffmpeg", "-y", "-i", os.path.abspath(input_path)]
    if vf_filters:
        cmd += ["-vf", filter_str]
    # Ensure audio is copied
    cmd += ["-c:a", "copy", os.path.abspath(output_path)]

    try:
        logger.info(f"🎞️ Applying Video FX: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return {"ok": True, "output_path": output_path, "effects": vf_filters}
        else:
            return {"ok": False, "error": result.stderr}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def register_tool(registry):
    registry.register("video_fx_tool", video_fx_tool)
