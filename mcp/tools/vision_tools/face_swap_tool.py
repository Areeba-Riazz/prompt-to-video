import os
import shutil
from typing import Any, Dict
from mcp.base_tool import BaseTool

_face_analyzer = None
_face_swapper_model = None

def _load_insightface_models() -> bool:
    global _face_analyzer, _face_swapper_model

    try:
        import insightface  # type: ignore
        from insightface.app import FaceAnalysis  # type: ignore

        if _face_analyzer is None:
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            _face_analyzer = FaceAnalysis(name="buffalo_l", providers=providers)
            _face_analyzer.prepare(ctx_id=0, det_size=(640, 640))
            print("[FaceSwap] FaceAnalysis (buffalo_l) loaded.")

        if _face_swapper_model is None:
            model_path = os.environ.get(
                "INSIGHTFACE_MODEL_PATH",
                "./models/insightface/inswapper_128.onnx",
            )
            if not os.path.exists(model_path):
                print(
                    f"[FaceSwap] inswapper_128.onnx not found at {model_path}. "
                    "Face swap will be skipped."
                )
                return False
            _face_swapper_model = insightface.model_zoo.get_model(
                model_path, download=False
            )
            print("[FaceSwap] inswapper_128.onnx loaded.")

        return True

    except Exception as e:
        print(f"[FaceSwap] InsightFace load failed: {e}. Swap will be skipped.")
        return False


class FaceSwapTool(BaseTool):
    @property
    def name(self) -> str:
        return "face_swapper"

    @property
    def description(self) -> str:
        return (
            "Maps a character's face from a reference image onto all faces in a target "
            "video, frame by frame, using InsightFace inswapper_128."
        )

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "source_face_image": "str — path to character portrait PNG",
            "target_video": "str — path to generated scene video",
            "output_path": "str — path to save face-swapped MP4",
        }

    @property
    def tags(self) -> list[str]:
        return ["video", "face_swap", "vision"]

    def execute(self, **kwargs) -> Any:
        source_face_image = kwargs.get("source_face_image", "")
        target_video = kwargs.get("target_video", "")
        output_path = kwargs.get("output_path", "")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        if not _load_insightface_models():
            print("[FaceSwap] Models unavailable — copying original video.")
            shutil.copy2(target_video, output_path)
            return output_path

        try:
            import cv2  # type: ignore

            src_img = cv2.imread(source_face_image)
            if src_img is None:
                raise RuntimeError(f"Cannot read source image: {source_face_image}")

            src_faces = _face_analyzer.get(src_img)
            if not src_faces:
                print("[FaceSwap] No face in source image — skipping swap.")
                shutil.copy2(target_video, output_path)
                return output_path

            source_face = src_faces[0]

            cap = cv2.VideoCapture(target_video)
            fps = cap.get(cv2.CAP_PROP_FPS) or 24
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            processed_frames = []
            frame_count = 0

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                frame_count += 1
                target_faces = _face_analyzer.get(frame)
                if target_faces:
                    for tgt_face in target_faces:
                        frame = _face_swapper_model.get(
                            frame, tgt_face, source_face, paste_back=True
                        )
                processed_frames.append(frame)

            cap.release()
            print(f"[FaceSwap] Processed {frame_count} frames.")

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(output_path, fourcc, fps, (w, h))
            for f in processed_frames:
                out.write(f)
            out.release()

            print(f"[FaceSwap] Output saved to {output_path}")
            return output_path

        except Exception as e:
            print(f"[FaceSwap] Swap failed: {e} — copying original video.")
            shutil.copy2(target_video, output_path)
            return output_path
