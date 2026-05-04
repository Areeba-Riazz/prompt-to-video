import logging
import os
import time
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from mcp.base_tool import BaseTool
from shared.utils.image_quality import is_acceptable_portrait_png, truncate_prompt_for_get_url

logger = logging.getLogger("ImageGenTool")

_URL_PROMPT_MAX = int(os.getenv("IMAGE_GEN_URL_PROMPT_MAX", "1100"))

# Pollinations: free tier rate-limits hard — retry with backoff across rounds.
_POLL_ROUNDS = int(os.getenv("IMAGE_GEN_POLL_ROUNDS", "8"))
_POLL_TIMEOUT = int(os.getenv("IMAGE_GEN_POLL_TIMEOUT", "120"))
_POLL_PER_SEED_TRIES = int(os.getenv("IMAGE_GEN_POLL_PER_SEED_TRIES", "4"))
_POLL_429_BACKOFF = float(os.getenv("IMAGE_GEN_POLL_429_BACKOFF", "15"))
_POLL_ROUND_SLEEP = float(os.getenv("IMAGE_GEN_POLL_ROUND_SLEEP", "20"))

_DEFAULT_HF_MODELS = (
    "black-forest-labs/FLUX.1-schnell,"
    "stabilityai/stable-diffusion-xl-base-1.0,"
    "runwayml/stable-diffusion-v1-5"
)


def _sleep_retry_after(resp, default: float) -> None:
    ra = resp.headers.get("Retry-After") if resp is not None else None
    if ra:
        try:
            time.sleep(min(float(ra), 180))
            return
        except (TypeError, ValueError):
            pass
    time.sleep(min(default, 180))


def _atomic_save_response_png(resp, output_path: str) -> bool:
    """Write HTTP image body to a temp file; move into place only if it passes portrait checks."""
    from PIL import Image

    if resp.status_code != 200 or not resp.content:
        return False
    tmp = output_path + ".tmp_poll.png"
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        try:
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            img.save(tmp, format="PNG")
        except Exception:
            with open(tmp, "wb") as f:
                f.write(resp.content)
        if is_acceptable_portrait_png(tmp):
            os.replace(tmp, output_path)
            return True
    finally:
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return False


def _pollinations_generate(url_prompt: str, output_path: str, existing_valid: bool) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    import requests
    import urllib.parse

    errors: List[str] = []
    seeds_cycle = [42, 77, 123, 201, 301, 555, 888]

    for round_idx in range(_POLL_ROUNDS):
        # Rotate starting seed each round so we don't hammer the same queue slot forever.
        seeds = seeds_cycle[round_idx % len(seeds_cycle) :] + seeds_cycle[: round_idx % len(seeds_cycle)]
        for seed in seeds:
            url = (
                "https://image.pollinations.ai/prompt/"
                f"{urllib.parse.quote(url_prompt)}"
                f"?width=768&height=768&seed={seed}&model=flux"
            )
            if len(url) > 7500:
                logger.warning("Pollinations URL still very long (%d chars); request may fail.", len(url))

            for attempt in range(_POLL_PER_SEED_TRIES):
                try:
                    resp = requests.get(url, timeout=_POLL_TIMEOUT)
                except requests.Timeout:
                    errors.append(f"r{round_idx}s{seed}a{attempt}_timeout")
                    time.sleep(min(8 * (attempt + 1), 45))
                    continue
                except requests.RequestException as exc:
                    errors.append(f"r{round_idx}s{seed}_transport:{exc!s}")
                    time.sleep(min(5 * (attempt + 1), 30))
                    continue

                if resp.status_code == 200 and _atomic_save_response_png(resp, output_path):
                    size = os.path.getsize(output_path)
                    return (
                        {
                            "ok": True,
                            "image_path": output_path,
                            "engine": f"pollinations:flux(seed={seed},round={round_idx})",
                            "size_bytes": size,
                        },
                        errors,
                    )

                if resp.status_code == 200:
                    errors.append(f"r{round_idx}s{seed}a{attempt}_bad_image")

                elif resp.status_code == 429:
                    errors.append(f"r{round_idx}s{seed}a{attempt}_429")
                    if existing_valid:
                        return (
                            {
                                "ok": True,
                                "image_path": output_path,
                                "engine": "kept_existing_image(rate_limited)",
                                "size_bytes": os.path.getsize(output_path),
                            },
                            errors,
                        )
                    _sleep_retry_after(resp, _POLL_429_BACKOFF * (attempt + 1))
                    continue

                else:
                    errors.append(f"r{round_idx}s{seed}a{attempt}_http{resp.status_code}")
                    break

        if round_idx < _POLL_ROUNDS - 1:
            gap = min(_POLL_ROUND_SLEEP * (1 + round_idx * 0.35), 120)
            logger.info(
                "Pollinations round %s/%s finished with no image; waiting %.0fs before next round.",
                round_idx + 1,
                _POLL_ROUNDS,
                gap,
            )
            time.sleep(gap)

    return None, errors


def _hf_models_list() -> List[str]:
    raw = os.getenv("HF_IMAGE_MODEL", _DEFAULT_HF_MODELS)
    return [m.strip() for m in raw.split(",") if m.strip()]


def _hf_via_inference_client(prompt: str, output_path: str, hf_token: str) -> Optional[Dict[str, Any]]:
    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        return None

    client = InferenceClient(token=hf_token)
    short_prompt = prompt[:2800]
    tmp = output_path + ".tmp_hfhub.png"
    try:
        for model in _hf_models_list():
            try:
                image = client.text_to_image(short_prompt, model=model)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                if hasattr(image, "save"):
                    image.save(tmp, format="PNG")
                elif isinstance(image, (bytes, bytearray)):
                    with open(tmp, "wb") as f:
                        f.write(image)
                else:
                    logger.warning("HF InferenceClient unexpected return type for model=%s", model)
                    continue
                if is_acceptable_portrait_png(tmp):
                    os.replace(tmp, output_path)
                    return {
                        "ok": True,
                        "image_path": output_path,
                        "engine": f"hf_hub:{model}",
                        "size_bytes": os.path.getsize(output_path),
                    }
                logger.warning("HF InferenceClient produced file failing portrait checks model=%s", model)
            except Exception as exc:
                logger.warning("HF InferenceClient failed model=%s: %s", model, exc)
    finally:
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return None


def _hf_via_http_post(prompt: str, output_path: str, hf_token: str) -> Optional[Dict[str, Any]]:
    import requests

    short_prompt = prompt[:2800]
    headers = {"Authorization": f"Bearer {hf_token}"}
    for model in _hf_models_list():
        urls = [
            f"https://router.huggingface.co/hf-inference/models/{model}",
            f"https://api-inference.huggingface.co/models/{model}",
        ]
        for url in urls:
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json={"inputs": short_prompt},
                    timeout=120,
                )
                if resp.status_code == 503:
                    logger.warning("HF model=%s loading (503) at %s — retry once after 20s", model, url)
                    time.sleep(20)
                    resp = requests.post(
                        url,
                        headers=headers,
                        json={"inputs": short_prompt},
                        timeout=120,
                    )
                if resp.status_code == 200 and _atomic_save_response_png(resp, output_path):
                    return {
                        "ok": True,
                        "image_path": output_path,
                        "engine": f"hf_http:{model}",
                        "size_bytes": os.path.getsize(output_path),
                    }
                if resp.status_code not in (200, 503):
                    logger.warning("HF HTTP %s for model=%s url=%s", resp.status_code, model, url)
            except Exception as exc:
                logger.warning("HF HTTP error model=%s url=%s: %s", model, url, exc)
    return None


def _generate_character_image(prompt: str, output_path: str) -> Dict[str, Any]:
    prompt = (prompt or "").strip()
    existing_valid = is_acceptable_portrait_png(output_path)
    url_prompt = truncate_prompt_for_get_url(prompt, max_chars=max(400, _URL_PROMPT_MAX))

    if len(prompt) > len(url_prompt):
        logger.warning(
            "Pollinations prompt shortened from %d to %d chars (GET URL limit). "
            "HF path still uses full prompt where supported.",
            len(prompt),
            len(url_prompt),
        )

    poll_ok, pollinations_errors = _pollinations_generate(url_prompt, output_path, existing_valid)
    if poll_ok:
        return poll_ok

    if pollinations_errors:
        logger.warning(
            "Pollinations exhausted (%s …)",
            "; ".join(pollinations_errors[:6]),
        )

    hf_token = os.getenv("HF_API_TOKEN", "").strip() or os.getenv("HF_TOKEN", "").strip()
    if hf_token:
        hub_result = _hf_via_inference_client(prompt, output_path, hf_token)
        if hub_result:
            return hub_result
        http_result = _hf_via_http_post(prompt, output_path, hf_token)
        if http_result:
            return http_result
    else:
        logger.warning(
            "No HF_TOKEN / HF_API_TOKEN — after Pollinations exhaustion there is no backup. "
            "Set a token and HF_IMAGE_MODEL (comma-separated fallbacks allowed)."
        )

    if existing_valid:
        return {
            "ok": True,
            "image_path": output_path,
            "engine": "kept_existing_image(fallback_avoided)",
            "size_bytes": os.path.getsize(output_path),
        }

    strict = os.getenv("IMAGE_GEN_STRICT", "").strip().lower() in ("1", "true", "yes")
    if strict:
        logger.error(
            "IMAGE_GEN_STRICT set — refusing local placeholder. Fix Pollinations/HF or network."
        )
        return {
            "ok": False,
            "image_path": output_path,
            "engine": "none",
            "error": "image_generation_failed_no_placeholder",
        }

    try:
        from PIL import Image, ImageDraw

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img = Image.new("RGB", (768, 768), color=(18, 25, 44))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, 768, 128), fill=(34, 48, 82))
        draw.text((28, 42), "Character portrait — generation failed", fill=(245, 248, 255))
        draw.text((28, 86), "See server logs (Pollinations / Hugging Face).", fill=(175, 210, 255))
        draw.ellipse((245, 170, 525, 450), fill=(96, 126, 176))
        draw.rectangle((300, 430, 470, 695), fill=(84, 114, 166))
        img.save(output_path, format="PNG")
        logger.error(
            "Wrote local placeholder PNG — remote generators failed. Last Pollinations tags: %s",
            "; ".join(pollinations_errors[-6:]) if pollinations_errors else "(none)",
        )
        return {
            "ok": True,
            "image_path": output_path,
            "engine": "local_stylized_fallback",
            "size_bytes": os.path.getsize(output_path),
        }
    except Exception as exc:
        return {"ok": False, "image_path": output_path, "error": str(exc)}


class ImageGenerationTool(BaseTool):
    @property
    def name(self) -> str:
        return "generate_character_image"

    @property
    def description(self) -> str:
        return "Generates a character portrait image from a prompt."

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "prompt": "str — description of the character",
            "output_path": "str — path to save the generated image",
        }

    @property
    def tags(self) -> list[str]:
        return ["vision", "image_gen"]

    def execute(self, **kwargs) -> Any:
        prompt = kwargs.get("prompt", "")
        output_path = kwargs.get("output_path", "")
        return _generate_character_image(prompt, output_path)


class QueryStockFootageTool(BaseTool):
    @property
    def name(self) -> str:
        return "query_stock_footage"

    @property
    def description(self) -> str:
        return "Queries reference visual styles or footage for character design."

    @property
    def input_schema(self) -> Dict[str, str]:
        return {"description": "str — description of the visual style"}

    @property
    def tags(self) -> list[str]:
        return ["vision", "reference"]

    def execute(self, **kwargs) -> Any:
        description = kwargs.get("description", "")
        return {
            "description": description,
            "references": [
                "Cyberpunk rain-lit alleys",
                "Noir portrait lighting",
                "High-contrast rooftop skyline",
            ],
        }
