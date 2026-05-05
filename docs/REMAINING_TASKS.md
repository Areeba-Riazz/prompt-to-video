# Project Montage: Remaining Tasks & Implementation Roadmap

This document outlines the remaining work required to fulfill the submission requirements for the Agentic AI Semester Project.

## 🔴 Critical Path: Missing Core Functionalities

### Phase 3 — Final Video Composition
*   [x] **Final Movie Stitches:** Implement the `compositor_tool.py` to merge all `scene_*.mp4` files into a single `final_output.mp4`.
*   [x] **Subtitle Overlay:** Implement the `subtitle_tool.py` using FFmpeg to burn subtitles into the final video.
*   [x] **Transitions:** Add simple fade or cross-dissolve transitions between scenes during the final compositing step.
*   [x] **Background Music (BGM):** Integrate background music selection or generation per scene mood (as per Phase 2 requirements).

### Phase 4 — Web Interface & Orchestration
*   [x] **Real-time Progress:** Implement WebSockets or Server-Sent Events (SSE) to show phase-level progress.
*   [x] **Phase-Level Re-runs:** Add UI buttons to regenerate specific components without re-running the entire pipeline.
*   [x] **Unified Dashboard:** Create a landing page or dashboard that orchestrates the entire flow.

### Phase 5 — Intelligent Edit & Undo System
*   [ ] **Intent Classification Agent:** Replace the current placeholder in `agents/edit_agent/intent_classifier.py` with a real LLM agent that parses natural language edits (e.g., "Make the scene darker").
*   [ ] **State Snapshot System:** Implement the `state_manager` logic to save JSON state and assets at every step (currently 0-byte files).
*   [ ] **Undo/Revert Logic:** Build the `revert(version)` functionality to restore previous snapshots.
*   [ ] **Version History UI:** Add a "History" panel in the frontend to display previous versions and allow one-click reverts.

---

## 🛠️ General Submission Requirements

### 🧪 Testing & Validation
*   [x] **Unit Tests:** Create a test suite in `tests/` covering:
    *   Phase 1: Script JSON schema validation.
    *   Phase 2: Audio duration and WAV merging.
    *   Phase 3: Video file integrity checks.
*   [x] **Integration Tests:** A full end-to-end run script (`scripts/test_pipeline.py` is completed and verified).

### 📂 Documentation & Artifacts
*   [ ] **Project Report (8–12 pages):** Must include system architecture, phase-wise implementation, JSON schemas, and challenges.
*   [ ] **Demo Video (3–7 minutes):** Showing the full pipeline, at least 3 edits, and 2 undo operations.
*   [ ] **Presentation Slides:** If prepared for the final demo.
*   [ ] **Sample Outputs:** Populate `data/outputs/` with high-quality sample audio, images, and video files.

---

## 👥 Responsibility Mapping (Based on Course Guidelines)

| Member | Primary Responsibility | Key Remaining Tasks |
| :--- | :--- | :--- |
| **Member 1** | Phase 1 — Story & Script | Finalize character roster consistency and unit tests. |
| **Member 2** | Phase 2 — Audio Generation | Background music integration and audio timing manifest. |
| **Member 3** | Phase 3 — Video & Composition | **Compositing tool**, subtitles, transitions, and A/V sync. |
| **Member 4** | Phase 4 & 5 — Web & Edit Agent | **WebSockets**, **State Manager (Snapshots)**, **Undo Logic**, and **Intent Agent**. |

---

## 📅 Deadline Checklist
- [x] Codebase structured and modular.
- [x] Root `README.md` updated with setup instructions.
- [ ] All 5 phases functional and integrated.
- [x] Requirements.txt complete.
- [x] Public/Shared GitHub Repo link ready.
