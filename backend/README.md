# Project Montage — Backend

The backend for Project Montage is a **FastAPI** application that orchestrates multi-agent workflows using **LangGraph**. It manages the transition from story prompts to structured scripts and eventually to synthesized video scenes.

## 🚀 Getting Started

### Prerequisites
*   [Python 3.11+](https://www.python.org/)
*   [FFmpeg](https://ffmpeg.org/) (Required for video compositing and audio muxing)

### Installation
```bash
# From the project root
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Development
`backend.app` is only importable when the **repository root** (the folder that contains `backend/`) is on Python’s module path—normally your current working directory.

```bash
# Recommended: current directory = repository root
python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000

# If your shell is already inside backend/, use the local module name (app.py adds the repo root to sys.path)
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
# equivalent: python app.py
```
The API documentation (Swagger UI) will be available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## 🧩 Architecture
The backend is organized into specialized agents and routes:
*   **`agents/`**: LangGraph nodes for Story, Audio, and Video generation. Includes the new **`PostProcAgent`** for surgical digital edits.
*   **`routes/`**: FastAPI routers for triggering and monitoring Phases 1, 2, and the new **Phase 5 (Intelligent Edit)**.
*   **`mcp/`**: Model Context Protocol (MCP) tool registry for handling external API calls and local processing (e.g., `audio_fx_tool`, `video_fx_tool`).

## ⚙️ Environment Variables
Create a `.env` file in the project root with the following keys:
*   `GOOGLE_API_KEY`: For script and character generation (Gemini).
*   `HF_TOKEN`: For AI video generation models.
*   `PEXELS_API_KEY`: For stock footage retrieval.
*   `PHASE1_OUTPUT_DIR`: Directory for script and character artifacts.
*   `PHASE2_OUTPUT_DIR`: Directory for audio and video artifacts.

## 🧪 CLI Tools
You can also run the agents directly without the web UI:
*   **Phase 1:** `python main.py`
*   **Phase 2:** `python scripts/run_phase2.py`

## 🎨 Phase 5: Post-Production Edit Suite
The backend now supports fine-grained, non-regenerative edits:
- **Audio FX**: `pitch_shift`, `tempo_adjustment`, `filter_type` (radio, telephone).
- **Video FX**: `brightness`, `contrast`, `saturation`, `filter_type` (grayscale, sepia).

These are handled by a modular **`Post_proc_node`** inserted at the end of the production graph, allowing for surgical adjustments without re-running expensive LLM or Video models.
