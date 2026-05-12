# Project completion roadmap — step-by-step implementation guide

This document is the **master roadmap** for finishing `prompt-to-video`: it aligns `docs/Agentic AI Final Project - 2026.pdf` with the **current repo layout**, preserves prior gap analysis, and adds **phase-by-phase, ordered implementation steps** (what to change, where, and how).

### Demo focus (your team’s priority)

The live demo centers on **video generation (Phase 3)** and the **edit agent + undo (Phase 5)**. Items are tagged so you ship what matters for that demo first.

| Tag | Meaning |
|-----|--------|
| **DEMO — P0** | Must-have for the video-gen + Phase 5 demo (do these first). |
| **P1** | Strongly supports the demo (compose, UI refresh, stable clips, env switching). |
| **P2** | Rubric / polish / course PDF alignment; schedule after P0/P1. |
| **DEFER** | Optional or report-only; safe to skip if time is tight — includes adding a separate **`story`** field to Phase 1 output (scenes + characters already satisfy the creative pipeline). |

**Suggested build order for demo week:** **§5 Phase 3 (video + compositor)** → **§7 Phase 5 (intent, execute, undo, no sticky env)** → **§6 Phase 4 (EditPanel + `onEditUpdate`)** → then P2/DEFER as time allows.

**How to use it:** Follow phases in order where dependencies exist (Phase 1 schema → Phase 2 manifest → Phase 3 sync → Phase 4 wiring → Phase 5 on top). Parallel work is noted per section.

---

## Table of contents

1. [Course acceptance checklist](#0-course-acceptance-checklist)
2. [Repository map (quick reference)](#1-repository-map-quick-reference)
3. [Cross-cutting prerequisites](#2-cross-cutting-prerequisites)
4. [Phase 1 — Story, script, characters](#3-phase-1--story-script-characters)
5. [Phase 2 — Audio generation](#4-phase-2--audio-generation)
6. [Phase 3 — Video generation & composition](#5-phase-3--video-generation--composition)  
   - [5.4 Peer baseline — high-mark cohort](#54-peer-baseline--high-mark-cohort-pexels--ffmpeg--per-clip-motion)
7. [Phase 4 — Web interface & orchestration](#6-phase-4--web-interface--orchestration)
8. [Phase 5 — Edit agent & undo](#7-phase-5--edit-agent--undo)
9. [Video pipeline: Pexels vs Wan (DashScope)](#8-video-pipeline-pexels-vs-wan-dashscope)
10. [Testing, demo & submission](#9-testing-demo--submission)
11. [Risks, timeline, definition of done](#10-risks-timeline-definition-of-done)
12. [Living implementation status](#12-living-implementation-status)

---

## 12. Living implementation status

*Last reviewed against the repo as of this doc update. Use this section to see what the roadmap already assumed vs what code has since gained.*

### Completed (matches or exceeds original roadmap gaps)

| Area | What exists today |
|------|-------------------|
| **Phase 3 — Merge & polish** | `compositor_tool.py`: scene merge, **xfade/fade** transitions, normalised clips. `compositor_node` in `agents/video_agent/agent.py`: per-scene subtitle burn, merge, BGM pass, writes `data/outputs/phase3/composition_metadata.json` and `final_output.mp4`. |
| **BGM beyond “first line only”** | When `BGM_USE_SMART_PLAN` is on (default in code path), `shared/bgm_plan.py` plans mood / volume / optional skip from **locations, dialogue, cues** (not only the first line). Phase 5 video edits can pass `_edit_bgm_mood` / `_edit_bgm_boost` and **`_compositor_bgm_only`** to remix BGM without re-burning subtitles when eligible. |
| **Phase 5 — Core API** | `backend/routes/phase5.py`: `/intent`, `/execute`, `/snapshot`, `/history`, `/revert`; disk restore via `edit_execution.restore_phase1_disk_from_state` on revert. Video-target branch restores **`COMPOSITOR_BGM`** with `try`/`finally` after temporary overrides. |
| **Phase 5 — Compositor-only return** | Execute returns merged state + **`next_step: "completed"`** and `final_output_path` when re-running compositor. |
| **Phase 4 — Edit UI glue** | `frontend/src/pages/Phase2.tsx` `onEditUpdate`: cache-bust nonces, **`liveCharDb`** so follow-up edits see updated voices, and when `nextStep === 'completed'` fetches **`/phase2/final/status`** to refresh composite metadata. |
| **Video sources** | `mcp/tools/video_tools/video_gen_tool.py`: **Pexels**, **DashScope Wan**, **HF** paths; `video_gen_node` still uses ordered **`VIDEO_GEN_METHODS`** fallback (not yet the dedicated `VIDEO_GEN_PIPELINE` switch from the roadmap). |
| **Phase 5 — Remove subtitles (no env leak)** | `remove_subtitles` sets **`state["_compositor_enable_subtitles"] = False`** before `compositor_node`; compositor reads that key and otherwise uses `COMPOSITOR_SUBTITLES` env — **no** `os.environ` mutation for subtitles (`backend/routes/phase5.py`, `agents/video_agent/agent.py`). |
| **Submission scaffolding** | `docs/REMAINING_TASKS.md`: Phases 3–5 checklist items marked done; unit tests + `scripts/test_pipeline.py` called out as present. |

### Partially done (still align with roadmap “P0/P1” follow-ups)

| Item | Notes |
|------|--------|
| **Compositor configuration** | Transition / default subtitle / BGM defaults still come from **`os.environ`** inside `compositor_node` unless overridden per call (`_compositor_enable_subtitles`, `_compositor_bgm_only`, `_edit_bgm_*`). Full “no env” compositor options remain roadmap Step 3.8. |
| **Edit → UI refresh** | **`completed`** path improved; branch that only updates when `newState.final_scenes` is set can still leave **`sceneResults`** unchanged for some partial Studio payloads — keep testing your demo script. |
| **`VIDEO_GEN_PIPELINE`** | Not implemented as a single primary selector; behaviour is still **`VIDEO_GEN_METHODS`** comma fallback in `agents/video_agent/agent.py`. |

### Not started / still open (roadmap unchanged)

| Item | Reference |
|------|-----------|
| **`timing_manifest.json`** | Phase 2 roadmap §4.2 — not emitted under `data/outputs/phase2/` yet. |
| **Ken Burns / per-clip pan–zoom** | Roadmap §5.4 — optional `SCENE_KEN_BURNS` / `zoompan` pass. |
| **Subtitles from timing manifest** | Roadmap Step 3.6 — subtitle timing still from `build_subtitle_manifest` + scene dialogue, not manifest file. |
| **Intent JSON schema validation** | Roadmap Step 5.1 — unknown `target` yields 400; structured field validation not centralised. |
| **Report / demo video / samples** | `docs/REMAINING_TASKS.md` unchecked. |

---

## 0. Course acceptance checklist

| Phase | Brief requirement | You must demonstrate |
|-------|-------------------|----------------------|
| **1** | LLM expands prompt → `{ story, scenes[], characters[] }` | Valid JSON; coherent script; consistent character names — **note:** top-level `story` text is **DEFER** for your demo; `scenes[]` + `characters[]` are enough to run Phases 2–3 |
| **2** | TTS per line + character voices; BGM; **timing manifest** | WAV per scene/line logic; mixed BGM; **`timing_manifest.json`** — **P2** for full PDF alignment; basic audio already runs without it |
| **3** | Images/video per scene; sync to audio; transitions; optional subtitles; **final MP4** | Scene clips + **`final_output.mp4`** — **DEMO — P0** |
| **4** | Full-stack UI; progress; **phase re-run** | Dashboard runs phases — **P1** (especially EditPanel path for Phase 5) |
| **5** | NL edits → intent; targeted re-run; **snapshots + undo** | Demo: **≥3 edits**, **≥2 undos** — **DEMO — P0** |
| **Artifacts** | README, tests, samples, report, demo video | All present in repo — **P2** for submission |

---

## 1. Repository map (quick reference)

| Phase | Key paths |
|-------|-----------|
| **1** | `agents/story_agent/agent.py`, `planner.py`, `agents/orchestrator/graph_phase1.py`, `shared/schemas/state.py`, `backend/routes/phase1.py`, `agents/edit_agent/agent.py` (validator, HITL) |
| **2** | `agents/audio_agent/agent.py`, `mcp/tools/audio_tools/` (`tts_tool.py`, `sfx_tool.py`, `bgm_tool.py`, `audio_merger.py`), `shared/schemas/phase2_state.py`, `backend/routes/phase2.py` |
| **3** | `agents/video_agent/agent.py`, `mcp/tools/video_tools/` (`video_gen_tool.py`, `compositor_tool.py`, `subtitle_tool.py`), `agents/post_proc_agent/agent.py` |
| **4** | `frontend/src/pages/Phase1.tsx`, `Phase2.tsx`, `Dashboard.tsx`, `backend/app.py`, `backend/routes/`, `backend/websocket/` |
| **5** | `agents/edit_agent/` (`intent_classifier.py`, `edit_execution.py`), `backend/routes/phase5.py`, `state_manager/`, `frontend/src/components/EditPanel.tsx` |

---

## 2. Cross-cutting prerequisites

**Priority:** **P1** — required before a reliable demo run.

### Step C1 — Environment and tooling

1. Copy `.env.example` → `.env` and set at minimum: LLM keys (`GOOGLE_API_KEY` / provider-specific), **`PEXELS_API_KEY`** and/or **`DASHSCOPE_API_KEY`** (video demo), `HF_TOKEN` if using HF video path.
2. Install **FFmpeg** and **ffprobe** on PATH; confirm `ffmpeg -version` and `ffprobe -version`.
3. Python: `pip install -r requirements.txt` (includes `dashscope` for Wan).

### Step C2 — Canonical handoff contract

1. **Phase 1 disk outputs** (read by Phase 2): `data/outputs/phase1/` — `scene_manifest.json`, `character_db.json`, `image_assets/*.png`.
2. After schema changes, update **`tests/unit/test_script_schema.py`** and any manifest loaders in `mcp/tools/system_tools/state_tool.py` or `get_task_graph` consumer.
3. Document the final JSON shapes in README (single source for the report). **DEFER** expanding docs until P0 video + Phase 5 work.

---

## 3. Phase 1 — Story, script, characters

**Overall priority for your demo:** **P2** (only touches video indirectly via better `visual_cue` / names). Do **not** block the video-gen or Phase 5 sprint on Phase 1 schema polish.

**Goal:** User prompt → structured script + roster that downstream phases can consume without ambiguity.

### 3.1 Gap summary

- **DEFER:** `MontageState` may lack a top-level **`story`** field — **not required** for your demo; the brief’s narrative can be described in the report using `scenes` alone.
- `ScriptwriterAgent` system prompt (`agents/story_agent/agent.py`) requests JSON with **`scenes`** — sufficient for Phases 2–5.
- **Fallback** (`agents/story_agent/planner.py`) is hardcoded “Kael & Sora” — unrelated to user prompts when LLM fails.
- **Character designer** assumes human portraits in prompts (`ImageSynthesizer`); animal/creature prompts get weak results.
- **Validator** (`agents/edit_agent/agent.py`) expects screenplay text with `INT./EXT.`, `CHAR:` lines, `[action]` — but **auto mode** skips validator (`route_input` → `scriptwriter` only when `input_mode != manual`). JSON `raw_script` may not match validator regex if manual path is used.

### 3.2 Implementation steps (order matters)

#### Step 1.1 — Extend Pydantic schema (`shared/schemas/state.py`) — **DEFER** for `story`; **P2** for `character_kind`

1. **DEFER — optional `story` / `logline`:** Skip unless the report explicitly requires a dedicated JSON field. Narrative summary can live in documentation or be inferred from scenes.
2. **P2 — recommended for better video (creatures / skip bad face-swap):** Extend **`Character`** with optional `character_kind` (`"human" | "animal" | "creature" | "other"`) so Phase 3 can gate face swap (see Phase 3 Step 3.4).
3. **P2 — optional:** Extend **`Scene`** with `tone` or `visual_keywords` for richer Wan/Pexels queries — only if you finish P0 video pipeline first.

**How:** Use Pydantic `Field(default=None)` for backward compatibility; update any `Scene(**dict)` construction to tolerate missing new keys.

#### Step 1.2 — Scriptwriter JSON contract (`agents/story_agent/agent.py`) — **DEFER**

1. **Do not prioritize** changing `_SYSTEM_PROMPT` to require a top-level `"story"` key for the demo.
2. If the course report insists on the literal `{ story, scenes[], characters[] }` shape, add **`story`** in one pass **after** Phase 3 + 5 are stable — or justify in the report that **synopsis = concatenation of scene headings + first lines**.

#### Step 1.3 — Instruct LLM for SFX-friendly dialogue — **P2**

1. In system prompt, require stage directions as **parentheses** for non-speech: e.g. `(laughs)`, `(door slams)` so `_parse_line_with_sfx` in Phase 2 splits correctly.
2. Discourage putting SFX only in italics or asterisks unless you extend the Phase 2 parser to handle them.

#### Step 1.4 — Scene count strategy — **P2**

1. Either: parse `NUMBER_OF_SCENES` as today, **or** add logic: `num_scenes = max(int(env), min_scenes_from_prompt_heuristic)` (e.g. count “,” or “and then” — optional).
2. Document for instructors: set `NUMBER_OF_SCENES=4` or `5` for multi-beat stories (rabbit/snail; cabin chaos).

#### Step 1.5 — Improve fallback scenes (`agents/story_agent/planner.py`) — **P2**

1. Replace static Kael/Sora with **prompt-derived** fallback: e.g. extract first clause of `prompt` as theme; use generic `Character A` / `Character B` with locations `EXT. LOCATION - DAY` matching keywords from prompt.
2. Keep at least **N** scenes where `N = int(os.environ.get("NUMBER_OF_SCENES", 3))`.

#### Step 1.6 — Character profiles for non-humans (`agents/story_agent/agent.py` — `CharacterDesigner._generate_ai_profile`) — **P2**

1. Extend the LLM prompt: if name or script suggests animal/creature, **appearance** may describe fur, species, stylization — not “human skin.”
2. In `_heuristic_character_profile`, add keyword buckets for `rabbit`, `snail`, `dog`, `cat`, etc., with short stylized descriptions (or delegate entirely to LLM when online).

#### Step 1.7 — Image synthesis branches (`ImageSynthesizer.synthesize`) — **P2**

1. If `character_kind == "animal"` or name matches animal regex, use prompts like: “stylized 3D render of a friendly rabbit character, head and shoulders, neutral background” — **avoid** “realistic human skin.”
2. For IP-sensitive names (“Tom”, “Jerry”), prefer **generic** “cartoon mouse / cartoon cat” in prompts to reduce policy issues.

#### Step 1.8 — Validator / manual mode (optional polish) — **DEFER**

1. If manual upload must pass validator, either generate `raw_script` in classic screenplay form from JSON scenes **before** validator, or relax validator to accept JSON mode.
2. Document: **instructor demo** should use **auto** mode with HITL approve — matches `backend/routes/phase1.py` flow.

#### Step 1.9 — Phase 1 tests — **P2**

1. Add/extend tests: schema validates important fields; scriptwriter parse accepts `scenes`; fallback produces N scenes. **DEFER** tests that only exist to assert a separate `story` field.

---

## 4. Phase 2 — Audio generation

**Overall priority for your demo:** **P2** (baseline TTS + mux already powers the video demo). Invest here **after** Phase 3 + 5 P0 items unless audio bugs block recording.

**Goal:** Per-scene dialogue audio with **distinct character voices**, **SFX** where scripted, optional **line-level timing**, and a **timing manifest** file; prepare clean inputs for mux/subtitles.

### 4.1 Gap summary

- No **`timing_manifest.json`** as required by the course PDF.
- `voice_synth_node` (`agents/audio_agent/agent.py`): SFX via `sfx_tool`; failures drop segments silently.
- BGM is applied later in **compositor**, not as a per-scene stem here — acceptable if documented; optional upgrade is per-scene beds.

### 4.2 Implementation steps

#### Step 2.1 — Segment timing collection (`agents/audio_agent/agent.py`) — **P2**

1. During the per-line loop, record **cumulative offset** in seconds before each segment:

   - After each concatenated segment, **probe duration** (`_wav_duration`) and append to a list: `{ "scene_id", "segment_index", "type": "speech|sfx", "file", "start_ms", "end_ms", "speaker": optional }`.

2. **start_ms** for segment `i` = sum of durations of segments `0..i-1` × 1000; **end_ms** = start + current duration × 1000.

#### Step 2.2 — Emit `timing_manifest.json` — **P2** (course PDF alignment; **not** blocking video-gen / Phase 5 demo if you subtitle via current path)

1. After all scenes processed, write:

   `data/outputs/phase2/timing_manifest.json`

   Suggested shape:

   ```json
   {
     "version": 1,
     "scenes": [
       {
         "scene_id": 1,
         "audio_path": ".../scene_01.wav",
         "duration_sec": 12.5,
         "segments": [
           { "start_ms": 0, "end_ms": 1200, "type": "sfx", "cue": "laughter" },
           { "start_ms": 1200, "end_ms": 4500, "type": "speech", "speaker": "Alice", "text": "Hello" }
         ]
       }
     ]
   }
   ```

2. Load path from env e.g. `PHASE2_TIMING_MANIFEST` or fixed relative path; **document** in README.

#### Step 2.3 — SFX robustness (`mcp/tools/audio_tools/sfx_tool.py` + voice synth) — **P2**

1. Add **cue normalization** map: `laughs` → `laughter`, `chuckles` → `laughter`, etc., before search.
2. On failure: optionally **synthesize** a short silence placeholder **or** very short generated tone (last resort) so duration doesn’t collapse; log warning.

#### Step 2.4 — Parser alignment (`_parse_line_with_sfx`) — **P2**

1. Optionally extend regex to handle `[laughs]` and `*laughs*` if Phase 1 emits them.
2. Unit tests: cover mixed `(sfx) dialogue (sfx)` lines.

#### Step 2.5 — Voice consistency — **P1** (helps edit demos like “change voice” sound convincing)

1. Confirm `character_db.json` fields (`edge_voice`, `tts_voice`, `kokoro_voice`, `gender`, `edge_pitch_offset_hz`) are populated in Phase 1 for **every** recurring speaker.
2. In `voice_synth_node`, if a speaker is missing from `char_db`, log error and use neutral defaults — avoid silent voice mixing.

#### Step 2.6 — Optional per-scene BGM stem (advanced) — **DEFER**

1. If course insists on **per-scene** BGM: after `scene_XX.wav` is built, run a **quiet** mood stem mix (from `bgm_tool` split logic or new helper) to `scene_XX_bed.wav`, then merge dialogue + bed before mux — **large change**; skip if you document **global BGM at composite** only.

#### Step 2.7 — Phase 2 tests — **P2**

1. Extend `tests/unit/test_audio_agent.py`: manifest segment sums equal total WAV duration within tolerance.
2. SFX tests already in `test_sfx_tool.py` — add normalization cases.

---

## 5. Phase 3 — Video generation & composition

**Overall priority for your demo:** **DEMO — P0** — This is the primary technical story for the recording.

**Goal:** Per-scene MP4s synced to dialogue, optional face consistency, then **merged** `final_output.mp4` with **transitions**, **subtitles**, **BGM**.

### 5.1 Gap summary

- `VIDEO_GEN_METHODS` is a **fallback chain**, not a clean **Pexels vs Wan** switch.
- Pexels cannot illustrate arbitrary plots (animals fighting, Tom/Jerry).
- Face swap assumes **human** faces — harmful for creatures/cartoons.
- ~~Compositor mood from **first** dialogue line only~~ — **improved:** `shared/bgm_plan.py` + `BGM_USE_SMART_PLAN` (see **§12**). Legacy path remains if smart plan is turned off.
- Phase 3 compositor often invoked only via **`POST /api/phase2/compose`** — UI must call it after Phase 2.

### 5.2 Implementation steps — upstream (video generation)

#### Step 3.1 — Env-driven pipeline selection (`agents/video_agent/agent.py` — `video_gen_node`) — **DEMO — P0**

1. Read **`VIDEO_GEN_PIPELINE`** (`pexels` | `wan` | `hf_ai`) — primary method for **all** scenes.
2. Optionally read **`VIDEO_GEN_FALLBACK_PIPELINE`** (single value or comma list). If primary fails (size &lt; `VIDEO_GEN_MIN_BYTES` or exception), try fallback **once** each.
3. **Backward compatibility:** If `VIDEO_GEN_PIPELINE` unset, derive order from existing `VIDEO_GEN_METHODS` string.

**Implementation sketch:**

```text
primary = os.environ.get("VIDEO_GEN_PIPELINE")
if not primary:
    methods = split VIDEO_GEN_METHODS
else:
    methods = [primary] + split(os.environ.get("VIDEO_GEN_FALLBACK_PIPELINE", ""))
```

4. Update `.env.example` and README with examples: stock-only vs Wan-only.

#### Step 3.2 — Harden Wan (`mcp/tools/video_tools/video_gen_tool.py` — `_generate_with_wan`) — **DEMO — P0**

1. Cap wait loop with **max wall time**; surface `FAILED` with clear error string.
2. After download, **ffprobe** duration; if `target_duration` set, **ffmpeg trim** (already partially done for Pexels path — mirror for Wan output).
3. Optional: map resolution via env `WAN_VIDEO_SIZE`.

#### Step 3.3 — Improve Pexels queries (`_generate_pexels_query`) — **DEMO — P0** (when using stock pipeline)

1. Pass **action verbs** from `visual_cue` (fight, race, airplane cabin) into LLM user prompt; add rule-based fallback keyword list for aviation, animals (generic stock: “two animals meadow” won’t match fight — accept limitation or force Wan).

#### Step 3.4 — Face swap gating (`agents/video_agent/agent.py` — `face_swap_node`) — **P1** (prevents ugly swaps on creature/cartoon demos)

1. Before `face_swapper`, check `character_kind` or heuristic: if non-human, **skip swap** and copy source to output (log `event: skipped_non_human`).
2. If `identity_validator` fails repeatedly, skip swap to avoid garbage output.

#### Step 3.5 — Lip sync / `USE_AI_ANIMATION` — **P1** (document before recording)

1. Document in README: SadTalker-style paths **replace** footage — bad for multi-character cabin scenes; recommend `USE_AI_ANIMATION=False` for instructor demos with ensemble stock/Wan.

### 5.3 Implementation steps — downstream (composition)

#### Step 3.6 — Subtitles from timing manifest (`mcp/tools/video_tools/subtitle_tool.py` + compositor) — **P2**

1. Change `build_subtitle_manifest` (or caller in `compositor_node`) to prefer **`timing_manifest.json`** segment **speech** rows for **accurate** `start_ms`/`end_ms` if manifest exists; fallback to current duration-derived logic.

#### Step 3.7 — Compositor mood (`agents/video_agent/agent.py` — `compositor_node`) — **P2**

1. Replace “first dialogue line emotion only” with: majority vote across scenes, or `scene[0].tone` from Phase 1 if added.

#### Step 3.8 — Parameterize compositor (remove env-only control) — **DEMO — P0** (required for clean Phase 5; removes sticky `COMPOSITOR_*` env)

1. Refactor `compositor_node(state, transition=..., transition_duration=..., enable_bgm=..., enable_subtitles=..., bgm_volume=...)` **or** pass via `StudioState` optional dict `compositor_options`.
2. `backend/routes/phase2.py` `/compose` and **`phase5.py`** pass explicit flags instead of mutating `os.environ` permanently.

#### Step 3.9 — Auto-compose after Phase 2 (optional UX) — **P1** (reduces “forgot to merge” during demo)

1. From `backend/routes/phase2.py` `/run`, optionally invoke `compositor_node` when `AUTO_COMPOSE_AFTER_PHASE2=1` — reduces missed final MP4.

#### Step 3.10 — Phase 3 tests — **P1**

1. `tests/unit/test_video_gen_tool.py`: mock methods order with `VIDEO_GEN_PIPELINE`.
2. Integration: given fake `final_scenes`, compositor produces file (existing patterns).

### 5.4 Peer baseline — high-mark cohort (Pexels + FFmpeg + per-clip motion)

**Priority:** **P1** for demo polish when using **Pexels** (stock often reads as “static slideshow” after stitch).

Another group scored very highly (~90) with an approach that closely matches part of our stack but adds one explicit polish step:

| What they did | How our repo compares |
|----------------|------------------------|
| **Pexels** for raw backgrounds / clips | Same: `mcp/tools/video_tools/video_gen_tool.py` (`method=pexels`). |
| **FFmpeg** (+ OpenCV “etc.”) to **stitch** | Same direction: `compositor_tool.py`, muxing, subtitles, BGM — heavy **FFmpeg**. Our **OpenCV** usage is mainly **face / identity** (`face_swap_tool.py`, `identity_tool.py`), not the main “make footage alive” pass. |
| Stitch looked **too static** → they added **panning and zoom** on the footage | We emphasize **scene-to-scene** transitions (`xfade` / fade in `compositor_tool.py`), **not** a default **Ken Burns–style** motion on **each** scene clip before merge. |

**Gap to close if you want their perceived quality on stock-only runs:** apply **per-scene motion** (slow zoom in/out, pan) so single clips feel cinematic — e.g. FFmpeg **`zoompan`** / scale+crop animation on each `scene_*.mp4` **after** download from Pexels and **before** lip-sync/mux or **before** final compositor merge. Optional env flag: `SCENE_KEN_BURNS=1` with tunable strength/duration.

**Implementation sketch (roadmap only):**

1. New helper or extend `ffmpeg_tool.py` / `video_fx_tool.py`: input clip + duration → output clip with `zoompan` limited to clip length.
2. Call from `video_gen_node` after successful Pexels path (not necessarily for Wan unless desired).
3. Document tradeoffs: re-encode cost, slight crop loss at edges.

---

## 6. Phase 4 — Web interface & orchestration

**Overall priority for your demo:** **P1** — mostly **glue** so Phase 3 output is visible and Phase 5 edits refresh the UI.

**Goal:** Clear path from prompt → HITL → Phase 2 → **Compose** → preview/download; progress visibility; phase re-run.

### 6.1 Gap summary

- Users may forget **`/compose`** — no `final_output.mp4`.
- Edit panel partial state updates (`Phase2.tsx` `onEditUpdate`) may not refresh previews for all code paths.

### 6.2 Implementation steps

#### Step 4.1 — Documented “happy path” (README) — **P1**

1. Numbered steps: Start backend → frontend → Phase 1 prompt → HITL approve → Phase 2 run → **Compose** → download `data/outputs/final_output.mp4`.

#### Step 4.2 — Phase 2 UI (`frontend/src/pages/Phase2.tsx`) — **P1**

1. After successful `/phase2/run`, show prominent **“Merge final video”** button if `final_output.mp4` missing or stale.
2. Optionally auto-call `/compose` when checkbox “Auto-merge final” is set.

#### Step 4.3 — Fix edit-driven refresh (`onEditUpdate`) — **DEMO — P0** (Phase 5 demo will look broken without this)

1. For **every** response from `/phase5/execute`:

   - Always `setRunNonce` / `setFinalVideoNonce`.
   - If `eData.data.final_output_path` or `final_scenes` present, **merge** into `sceneResults` via `dedupeScenesById`.
   - If `next_step === 'completed'` (compositor-only), **fetch** or set final video URL from `eData.data.final_output_path`.

2. Ensure `currentState` passed to EditPanel includes **`final_output_path`** when available (lift state from parent).

#### Step 4.4 — WebSocket / SSE (`backend/websocket/`, `frontend/src/hooks/useProgress.ts`) — **P2**

1. Verify progress events fire during long Phase 2 nodes (voice, video gen, Wan). If gaps, add `report_progress` calls in slow loops.
#### Step 4.5 — API base URL — **P2**

1. Replace hardcoded `http://localhost:8000` in `EditPanel.tsx` with `import.meta.env.VITE_API_URL` + fallback for production builds.

#### Step 4.6 — Dashboard (`frontend/src/pages/Dashboard.tsx`) — **DEFER**

1. Ensure navigation links land on Phase 1/2 with consistent state; optional “reset outputs” dev button (clear `data/outputs` warning).

---

## 7. Phase 5 — Edit agent & undo

**Overall priority for your demo:** **DEMO — P0** — co-equal with Phase 3 for what you show on camera.

**Goal:** NL → structured intent → correct **targeted** pipeline branch → **snapshot** → **revert** restores disk + JSON state.

### 7.1 Gap summary

- ~~`phase5.py` still sets `os.environ["COMPOSITOR_SUBTITLES"]` for `remove_subtitles`~~ — **fixed:** scoped **`_compositor_enable_subtitles`** on `StudioState` (see **§12**). **`COMPOSITOR_BGM`** overrides still use `try`/`finally` on the video-edit path.
- `post_proc_node` needs **`final_scenes` hydrated** from disk when skipping upstream nodes (`edit_execution.hydrate_final_scenes_for_post_proc`).
- Intent JSON from LLM may be invalid — needs validation + user-facing errors.

### 7.2 Implementation steps

#### Step 5.1 — Intent schema validation (`backend/routes/phase5.py` or `edit_execution.py`) — **DEMO — P0**

1. After `classify_edit_intent`, validate **required keys**: `intent`, `target`, `scope`, `parameters` (dict).
2. Whitelist `target` ∈ `{ script, audio, audio_fx, video_frame, video_fx, video }`; reject unknown with 400.

#### Step 5.2 — Pass compositor flags explicitly — **DEMO — P0** (pairs with Phase 3 Step 3.8) — **subtitles done**

1. ~~Refactor `remove_subtitles` branch~~ **Done:** `state["_compositor_enable_subtitles"] = False` + compositor reads it; no `os.environ` for subtitles.
2. Remaining: other `COMPOSITOR_*` / transition / BGM env → full state bag (Step 3.8).

#### Step 5.3 — Golden-path tests per target (`tests/unit/test_edit_execution.py` + integration) — **P1**

1. **script:** calls `ScriptwriterAgent.generate` — mock LLM.
2. **audio:** `apply_audio_target_to_state` marks dirty characters/scenes.
3. **video_frame:** scope `scene:N` updates scene visual fields.
4. **video:** invokes compositor with mocked registry.
5. **audio_fx / video_fx:** `post_proc_map` keys `scene:` / `global` / `character:` expansion.

#### Step 5.4 — Undo reliability (`state_manager/snapshot.py`) — **DEMO — P0**

1. After `revert`, verify `restore_phase1_disk_from_state` runs and UI reloads manifest paths.
2. Add integration test: snapshot v1 → edit → snapshot v2 → revert v1 → file hashes match v1.

#### Step 5.5 — Intent classifier robustness (`agents/edit_agent/intent_classifier.py`) — **DEMO — P0**

1. Add few-shot examples for: “remove subtitles”, “add BGM”, “faster scene 2”, “regenerate scene 1 visuals”.
2. Lower temperature for classification (already ~0.2).

#### Step 5.6 — Frontend snapshot after edit (`EditPanel.tsx`) — **P1**

1. Already snapshots after execute — ensure **`truncate_after_version`** when branching from middle history works (existing logic).

---

## 8. Video pipeline: Pexels vs Wan (DashScope)

**Priority:** **DEMO — P0** — this section is the conceptual spine for Phase 3 Step 3.1.

### Summary table

| Concern | Pexels | Wan (DashScope) |
|---------|--------|------------------|
| **Best for** | Real humans, locations, generic B-roll | Imaginative / animal / impossible scenes |
| **Env** | `PEXELS_API_KEY` | `DASHSCOPE_API_KEY`, `dashscope` package |
| **Cost/latency** | Lower / faster | Higher / slower |
| **Implementation** | `method=pexels` in `video_gen_tool` | `method=dashscope`, model `wan2.1-t2v-plus` |

### Single-switch behavior (recommended)

1. Implement **`VIDEO_GEN_PIPELINE`** as in **§5.2 Step 3.1**.
2. Instructor eval: for creative prompts, set `VIDEO_GEN_PIPELINE=wan`; for stock demos, `pexels`.

---

## 9. Testing, demo & submission

**Demo-first testing:** prioritize **`tests/unit/test_video_gen_tool.py`**, compositor smoke, **`test_intent_agent.py`**, **`test_edit_execution.py`**, and a dry-run of EditPanel + undo before polishing Phase 1/2-only tests.

### Step T1 — Unit tests (per brief)

| Phase | File / area | Demo priority |
|-------|-------------|----------------|
| 1 | `tests/unit/test_script_schema.py` | **P2** |
| 2 | `tests/unit/test_audio_agent.py`, `test_sfx_tool.py` | **P2** |
| 3 | `tests/unit/test_video_gen_tool.py`, compositor smoke | **P1** |
| 5 | `tests/unit/test_intent_agent.py`, `test_edit_execution.py` | **P1** |

### Step T2 — Integration

1. Extend `scripts/test_pipeline.py` (or add `scripts/test_e2e.py`): Phase 1 → 2 → compose → assert `final_output.mp4` exists and size &gt; threshold — **P1** before recording.

### Step T3 — Demo video (3–7 min) — **DEMO — P0 deliverable**

1. Record: prompt → HITL → full pipeline → **three** distinct edits (voice / scene visual / subtitle or BGM) → **two** undos.
2. Keep instructor prompts in a doc for reproducibility.

### Step T4 — Report & samples — **P2** (submission deadline)

1. Report 8–12 pages: architecture, **JSON schemas**, APIs, challenges, results, contributions.
2. Place sample outputs under `data/outputs/` (gitignore large binaries if needed; use Git LFS or external link per course rules).

---

## 10. Risks, timeline, definition of done

### Risks

| Risk | Mitigation |
|------|------------|
| Wan timeout | Max wait + clear UI error; retry once |
| Pexels irrelevant footage | Wan pipeline + better visual cues in Phase 1 |
| Face swap on animals | Skip swap for non-human |
| Global env in API | Pass options into `compositor_node` |

### Suggested timeline — **demo-first** (video gen + Phase 5)

| Week | Focus |
|------|--------|
| **1** | **Phase 3:** `VIDEO_GEN_PIPELINE`, Wan hardening, Pexels queries; **Phase 5:** intent validation, compositor flags (Steps 3.8 + 5.2), **`phase5.py` env leak fix** |
| **2** | **Phase 4:** `onEditUpdate` refresh (**Step 4.3**); merge/final video UX (**4.2**); **Phase 5:** undo + classifier few-shots + golden-path tests |
| **3** | Face-swap gating / README for lip-sync; Phase 3 tests; rehearse **demo script** (3 edits, 2 undos) |
| **4** | **P2:** timing manifest, Phase 1 polish (NOT `story` unless report demands), Phase 2 SFX — only if rubric time remains |
| **5** | Report, samples, optional E2E automation |

### Definition of done — **aligned to your demo**

1. **DEMO — P0:** **`VIDEO_GEN_PIPELINE`** switches Pexels vs Wan via `.env`; **`final_output.mp4`** looks intentional for your chosen prompt; Phase 5 runs **≥3 edits + ≥2 undos** on camera without stale UI.
2. **P1:** Compositor options passed explicitly (no sticky globals); EditPanel refresh works for **all** `next_step` values.
3. **P2 / rubric:** `timing_manifest.json` (or documented substitute); README + tests + report + recorded demo; optional **`story`** JSON field **DEFER** unless course explicitly penalizes absence.

---

## References

- `docs/Agentic AI Final Project - 2026.pdf`
- `.env.example`
- `docs/REMAINING_TASKS.md` (may be partially outdated)

---

*Document version: 2.4 — remove-subtitles uses `_compositor_enable_subtitles` (no sticky env).*
