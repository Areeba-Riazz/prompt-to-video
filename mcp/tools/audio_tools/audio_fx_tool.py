import os
import subprocess
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("AudioFXTool")

def audio_fx_tool(
    input_path: str,
    output_path: str,
    pitch: Optional[float] = 1.0,  # 1.0 = normal, 0.8 = lower, 1.2 = higher
    speed: Optional[float] = 1.0,  # 1.0 = normal, 1.5 = faster
    volume: Optional[float] = 1.0, # 1.0 = normal
    filter_type: Optional[str] = None # "radio", "telephone", "reverb"
) -> Dict[str, Any]:
    """
    Applies post-production audio effects using ffmpeg.
    """
    if not os.path.exists(input_path):
        return {"ok": False, "error": f"Input file not found: {input_path}"}

    filters = []

    # 1. Volume
    if volume != 1.0:
        filters.append(f"volume={volume}")

    # 2. Pitch & Speed (Modular approach)
    # Pitch shift without changing duration is tricky with vanilla ffmpeg filters.
    # We use a combo of asetrate and atempo.
    if pitch != 1.0:
        # To lower pitch (0.8): lower sample rate, then speed up back to normal
        # To raise pitch (1.2): raise sample rate, then slow down back to normal
        sample_rate = 44100
        new_rate = int(sample_rate * pitch)
        tempo = 1.0 / pitch
        filters.append(f"asetrate={new_rate}")
        # ffmpeg atempo only supports 0.5 to 2.0. We may need to chain them if extreme.
        if tempo < 0.5:
            filters.append("atempo=0.5,atempo=" + str(tempo/0.5))
        elif tempo > 2.0:
            filters.append("atempo=2.0,atempo=" + str(tempo/2.0))
        else:
            filters.append(f"atempo={tempo}")

    # 3. Speed (tempo adjustment without pitch change)
    if speed != 1.0:
        if speed < 0.5:
            filters.append("atempo=0.5,atempo=" + str(speed/0.5))
        elif speed > 2.0:
            filters.append("atempo=2.0,atempo=" + str(speed/2.0))
        else:
            filters.append(f"atempo={speed}")

    # 4. Filter Presets
    if filter_type == "radio":
        # High pass + low pass + slight distortion (using overdrive/flanger or just EQ)
        filters.append("highpass=f=500,lowpass=f=3000,anequalizer=c0 f=1000 g=10 t=1")
    elif filter_type == "telephone":
        filters.append("highpass=f=400,lowpass=f=3400,equalizer=f=1000:width_type=h:width=200:g=10")
    elif filter_type == "reverb":
        filters.append("aecho=0.8:0.88:60:0.4")

    filter_str = ",".join(filters) if filters else "copy"
    
    cmd = ["ffmpeg", "-y", "-i", os.path.abspath(input_path)]
    if filters:
        cmd += ["-af", filter_str]
    cmd += [os.path.abspath(output_path)]

    try:
        logger.info(f"🔊 Applying Audio FX: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return {"ok": True, "output_path": output_path, "effects": filters}
        else:
            return {"ok": False, "error": result.stderr}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def register_tool(registry):
    registry.register("audio_fx_tool", audio_fx_tool)
