"""
Face Swap — models/face_swap.py
MCP Tool Names: face_swapper, identity_validator

Priority chain:
  1. InsightFace inswapper_128.onnx — frame-by-frame face mapping
  2. Graceful skip                  — log warning and return original video
"""

import os
import shutil
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Model cache (avoid reloading on every call)
# ─────────────────────────────────────────────────────────────────────────────

_face_analyzer = None
_face_swapper_model = None


def _load_insightface_models() -> bool:
    """
    Lazy-load InsightFace FaceAnalysis + inswapper_128 models.
    Returns True if loaded successfully, False otherwise.
    """
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


# ─────────────────────────────────────────────────────────────────────────────
# Public: identity_validator
# ─────────────────────────────────────────────────────────────────────────────

def validate_identity(image_path: str) -> bool:
    """
    MCP Tool: identity_validator
    Checks that at least one face is detectable in a character reference image.

    Args:
        image_path: Path to a PNG character portrait.

    Returns:
        True if a face is detected, False otherwise.
    """
    if not _load_insightface_models():
        # Can't validate without models — return True to avoid blocking pipeline
        print("[FaceSwap] Skipping validation (models not available) — assuming valid.")
        return True

    try:
        import cv2  # type: ignore
        img = cv2.imread(image_path)
        if img is None:
            print(f"[FaceSwap] Cannot read image: {image_path}")
            return False
        faces = _face_analyzer.get(img)
        result = len(faces) > 0
        print(f"[FaceSwap] Identity validation: {'PASS' if result else 'FAIL'} — {image_path}")
        return result
    except Exception as e:
        print(f"[FaceSwap] Validation error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Public: face_swapper
# ─────────────────────────────────────────────────────────────────────────────

def swap_face_in_video(
    source_face_image: str,
    target_video: str,
    output_path: str,
) -> str:
    """
    MCP Tool: face_swapper
    Maps a character's face from a reference image onto all faces in a target
    video, frame by frame, using InsightFace inswapper_128.

    Falls back to copying the original video if InsightFace is unavailable.

    Args:
        source_face_image: Path to character portrait PNG.
        target_video: Path to generated scene video.
        output_path: Where to save the face-swapped MP4.

    Returns:
        Path to face-swapped (or original) video.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if not _load_insightface_models():
        print("[FaceSwap] Models unavailable — copying original video.")
        shutil.copy2(target_video, output_path)
        return output_path

    try:
        import cv2  # type: ignore

        # Validate + load source face
        src_img = cv2.imread(source_face_image)
        if src_img is None:
            raise RuntimeError(f"Cannot read source image: {source_face_image}")

        src_faces = _face_analyzer.get(src_img)
        if not src_faces:
            print("[FaceSwap] No face in source image — skipping swap.")
            shutil.copy2(target_video, output_path)
            return output_path

        source_face = src_faces[0]

        # Read all frames from target video
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

        # Write output
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
