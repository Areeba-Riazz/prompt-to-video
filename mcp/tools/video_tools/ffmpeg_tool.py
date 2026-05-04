import subprocess
from typing import Any, Dict
from mcp.base_tool import BaseTool

class FFmpegTool(BaseTool):
    @property
    def name(self) -> str:
        return "ffmpeg_processor"

    @property
    def description(self) -> str:
        return "Runs arbitrary FFmpeg commands safely for video composition and processing."

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "cmd": "list — The FFmpeg command arguments as a list of strings",
        }

    @property
    def tags(self) -> list[str]:
        return ["video", "ffmpeg", "system"]

    def execute(self, **kwargs) -> Any:
        cmd = kwargs.get("cmd", [])
        if not cmd or cmd[0] != "ffmpeg":
            return {"ok": False, "error": "Invalid command. Must start with 'ffmpeg'."}

        print(f"[FFmpegTool] Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            if result.returncode == 0:
                return {"ok": True, "output": result.stdout.decode()}
            else:
                return {"ok": False, "error": result.stderr.decode()}
        except Exception as e:
            return {"ok": False, "error": str(e)}
