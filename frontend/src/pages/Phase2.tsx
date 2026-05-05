import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useProgress } from '../hooks/useProgress';

interface Phase2SceneResult {
  scene_id: number;
  raw_mp4_path?: string;
  final_video_path?: string;
  error?: string;
}
interface DialogueLine { speaker: string; line: string; visual_cue?: string; }
interface Scene { scene_id: number; location: string; characters: string[]; dialogue: DialogueLine[]; }
interface Character { name: string; appearance_description: string; personality_traits: string[]; reference_style: string; image_path?: string; }

const API = 'http://localhost:8000/api';

function dedupeScenesById(scenes: Phase2SceneResult[]): Phase2SceneResult[] {
  const m = new Map<number, Phase2SceneResult>();
  for (const s of scenes) {
    m.set(s.scene_id, s);
  }
  return [...m.entries()].sort((a, b) => a[0] - b[0]).map(([, v]) => v);
}

// ── Scene accordion item ─────────────────────────────────────────────────────
const SceneAccordion = ({
  result,
  refScene,
  videoNonce,
  onRegen,
  isRegenerating = false,
}: {
  result: Phase2SceneResult;
  refScene?: Scene;
  videoNonce: number;
  onRegen: (sceneId: number) => void;
  isRegenerating?: boolean;
}) => {
  const [open, setOpen] = useState(false);
  const mp4Path = result.raw_mp4_path || result.final_video_path;
  const videoSrc = !result.error && mp4Path
    ? `${API}/phase2/video/${result.scene_id}?v=${videoNonce}`
    : null;

  return (
    <div className="p2-acc">
      <button className={`p2-acc-hd ${open ? 'p2-acc-hd--open' : ''}`} onClick={() => setOpen(o => !o)}>
        <div className="p2-acc-left">
          <span className="p2-acc-icon">{isRegenerating ? '⏳' : result.error ? '❌' : '🎬'}</span>
          <div>
            <div className="p2-acc-title">Scene {result.scene_id}</div>
            {refScene && <div className="p2-acc-loc">{refScene.location}</div>}
          </div>
        </div>
        <div className="p2-acc-right">
          {isRegenerating ? (
            <span className="p2-acc-badge p2-acc-badge--loading">GENERATING…</span>
          ) : (
            <span className={`p2-acc-badge ${result.error ? 'p2-acc-badge--err' : 'p2-acc-badge--ok'}`}>
              {result.error ? 'ERROR' : 'READY'}
            </span>
          )}
          <span className="p2-acc-chevron">{open ? '▲' : '▼'}</span>
        </div>
      </button>

      {open && (
        <div className="p2-acc-body">
          {isRegenerating ? (
            <div className="p2-regen-loading">
              <div className="p2-spinner" />
              <span>Regenerating Scene {result.scene_id}…</span>
            </div>
          ) : result.error ? (
            <div className="p2-scene-error">⚠️ {result.error}</div>
          ) : (
            <>
              {videoSrc && (
                <div className="p2-video-wrap">
                  <video
                    className="p2-video"
                    key={`${result.scene_id}-${videoNonce}`}
                    src={videoSrc}
                    controls
                    preload="metadata"
                  />
                </div>
              )}
              {!videoSrc && (
                <div className="p2-no-video">No video file available for this scene.</div>
              )}
            </>
          )}

          {refScene && (
            <div className="p2-scene-script">
              <div className="p2-scene-script-lbl">Script & Actions</div>
              {refScene.dialogue.map((d, i) => (
                <div key={i} className="p2-script-line">
                  <div className="p2-script-spk">{d.speaker}</div>
                  <div className="p2-script-body">
                    <div className="p2-script-txt">"{d.line}"</div>
                    {d.visual_cue && (
                      <div className="p2-script-cue">
                        <span>🎥</span>
                        <span className="p2-script-cue-txt">{d.visual_cue}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div style={{ padding: '12px', borderTop: '1px solid #1e1e22', display: 'flex', justifyContent: 'flex-end' }}>
                <button 
                  className="p2-btn-regen" 
                  style={{ padding: '6px 12px', fontSize: '11px' }}
                  onClick={() => onRegen(result.scene_id)}
                >
                  🔄 Regenerate Scene {result.scene_id}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ── Main Phase2 page ─────────────────────────────────────────────────────────
const Phase2 = () => {
  const navigate = useNavigate();
  const progress = useProgress();
  const [loading, setLoading] = useState(false);
  const [loadingStepIdx, setLoadingStepIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [sceneResults, setSceneResults] = useState<Phase2SceneResult[]>([]);
  const [phase2Done, setPhase2Done] = useState(false);
  const [refScript, setRefScript] = useState<{ scenes: Scene[] } | null>(null);
  const [refChars, setRefChars] = useState<Character[]>([]);

  const loadRef = useCallback(async () => {
    try {
      const [sr, cr] = await Promise.all([fetch(`${API}/phase1/script`), fetch(`${API}/phase1/characters`)]);
      if (sr.ok) { const d = await sr.json(); if (d.data?.scenes) setRefScript({ scenes: d.data.scenes }); }
      if (cr.ok) { const d = await cr.json(); if (d.data) setRefChars(d.data); }
    } catch { /* Phase 1 not yet run */ }
  }, []);

  const [sidebarOpen, setSidebarOpen] = useState(false);
  /** Bumps when a run finishes so `<video>` URLs don't stick to cached prior responses in the browser. */
  const [runNonce, setRunNonce] = useState(0);
  /** Which single scene is currently being regenerated (null = full run). */
  const [regeneratingSceneId, setRegeneratingSceneId] = useState<number | null>(null);

  const loadOutputsFromDisk = useCallback(async () => {
    try {
      const res = await fetch(`${API}/phase2/outputs`);
      if (res.ok) {
        const d = await res.json();
        if (d.data?.scenes?.length) {
          setSceneResults(dedupeScenesById(d.data.scenes));
          setPhase2Done(true);
          setRunNonce((n) => n + 1);
        }
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { void loadRef(); }, [loadRef]);

  useEffect(() => {
    if (progress?.phase === 'phase2') {
      const steps = ['Video Gen', 'Voice Synth', 'Face Swap', 'Lip Sync'];
      const idx = steps.indexOf(progress.step);
      if (idx !== -1 && loading) {
        setLoadingStepIdx(idx);
      }
    }
  }, [progress, loading]);

  const handleRun = async (sceneId: number | null = null) => {
    setLoading(true);
    setError(null);
    if (sceneId) {
      // Single-scene regen — keep existing results visible, just mark this scene loading
      setRegeneratingSceneId(sceneId);
    } else {
      // Full run — wipe everything
      setSceneResults([]);
      setRegeneratingSceneId(null);
      setPhase2Done(false);
    }
    try {
      const res = await fetch(`${API}/phase2/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_id: sceneId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Phase 2 failed');
      if (sceneId && data.data?.scenes) {
        setSceneResults(prev => dedupeScenesById([...prev, ...data.data.scenes]));
      } else if (data.data?.scenes) {
        setSceneResults(dedupeScenesById(data.data.scenes));
      }
      setPhase2Done(true);
      setRunNonce(n => n + 1);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'An error occurred');
    } finally {
      setLoading(false);
      setRegeneratingSceneId(null);
    }
  };

  const agents = [
    { icon: '🎥', name: 'Video Gen' }, { icon: '🎤', name: 'Voice Synth' },
    { icon: '👤', name: 'Face Swap' }, { icon: '🔊', name: 'Lip Sync' },
  ];

  const getRefScene = (id: number) => refScript?.scenes.find(s => s.scene_id === id);

  const displayScenes = useMemo(() => dedupeScenesById(sceneResults), [sceneResults]);

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=DM+Sans:wght@300;400;500&family=DM+Mono:wght@400&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        @keyframes pulse { 0%,100%{ opacity:1; } 50%{ opacity:0.5; } }
        @keyframes spin { to { transform: rotate(360deg); } }

        .p2-root { display: flex; min-height: 100vh; background: #0a0a0b; color: #e8e0d0; font-family: 'DM Sans', sans-serif; position: relative; overflow-x: hidden; }

        /* Sidebar Right (Script) */
        .p2-script-side { position: fixed; top: 0; right: 0; bottom: 0; width: 340px; background: #111113; border-left: 1px solid #1e1e22; transform: translateX(100%); transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1); z-index: 1000; display: flex; flex-direction: column; }
        .p2-script-side--open { transform: translateX(0); box-shadow: -20px 0 50px rgba(0,0,0,0.5); }
        .p2-script-side-hd { padding: 24px; border-bottom: 1px solid #1e1e22; display: flex; align-items: center; justify-content: space-between; }
        .p2-script-side-title { font-family: 'Playfair Display', serif; font-size: 18px; font-weight: 600; color: #f0e8d8; }
        .p2-script-side-close { background: none; border: none; color: #4a4a55; cursor: pointer; font-size: 18px; }
        .p2-script-side-body { flex: 1; overflow-y: auto; padding: 24px; }
        .p2-script-side-scene { margin-bottom: 24px; }
        .p2-side-scene-id { font-family: 'DM Mono', monospace; font-size: 10px; color: #6e9ec8; margin-bottom: 4px; }
        .p2-side-scene-loc { font-size: 12px; color: #b0a898; font-weight: 600; margin-bottom: 8px; }

        .p2-script-toggle { position: fixed; right: 24px; bottom: 24px; width: 56px; height: 56px; border-radius: 50%; background: #6e9ec8; color: #fff; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 20px; z-index: 900; box-shadow: 0 4px 15px rgba(110,158,200,0.4); transition: transform 0.2s; }
        .p2-script-toggle:hover { transform: scale(1.05); }

        /* Sidebar Left */
        .p2-sidebar { width: 240px; min-width: 240px; position: fixed; top: 0; left: 0; bottom: 0; background: #111113; border-right: 1px solid #1e1e22; display: flex; flex-direction: column; padding: 28px 0 24px; z-index: 100; }
        .p2-logo { padding: 0 24px 28px; border-bottom: 1px solid #1e1e22; }
        .p2-logo-eyebrow { font-family: 'DM Mono', monospace; font-size: 9px; letter-spacing: 0.2em; text-transform: uppercase; color: #6e9ec8; margin-bottom: 4px; }
        .p2-logo-title { font-family: 'Playfair Display', serif; font-size: 20px; font-weight: 700; color: #f0e8d8; }
        .p2-nav-sec { padding: 20px 24px 16px; border-bottom: 1px solid #1e1e22; }
        .p2-sec-lbl { font-size: 9px; letter-spacing: 0.15em; text-transform: uppercase; color: #4a4a55; margin-bottom: 12px; }
        .p2-agent-row { display: flex; align-items: center; gap: 10px; padding: 7px 0; }
        .p2-agent-icon { font-size: 13px; width: 20px; text-align: center; }
        .p2-agent-name { flex: 1; font-size: 13px; color: #b0a898; }
        .p2-agent-dot { width: 6px; height: 6px; border-radius: 50%; }
        .p2-agent-dot.idle { background: #4a4a55; }
        .p2-agent-dot.running { background: #6e9ec8; animation: pulse 2s infinite; }
        .p2-agent-dot.done { background: #4a9e6f; }
        .p2-sidebar-footer { margin-top: auto; padding: 16px 24px 0; border-top: 1px solid #1e1e22; font-size: 10px; color: #3a3a44; font-family: 'DM Mono', monospace; }

        /* Main */
        .p2-main { margin-left: 240px; flex: 1; display: flex; flex-direction: column; }
        .p2-topbar { position: sticky; top: 0; z-index: 50; background: rgba(10,10,11,0.92); backdrop-filter: blur(8px); border-bottom: 1px solid #1e1e22; padding: 0 40px; height: 52px; display: flex; align-items: center; justify-content: space-between; }
        .p2-breadcrumb { font-family: 'DM Mono', monospace; font-size: 11px; color: #4a4a55; display: flex; align-items: center; gap: 8px; }
        .p2-breadcrumb span { color: #6e9ec8; }
        .p2-phase-badge { font-family: 'DM Mono', monospace; font-size: 10px; letter-spacing: 0.12em; background: rgba(110,158,200,0.12); color: #6e9ec8; border: 1px solid rgba(110,158,200,0.25); border-radius: 4px; padding: 4px 10px; text-transform: uppercase; }
        .p2-content { padding: 48px 40px 80px; max-width: 880px; }

        /* Hero */
        .p2-hero { margin-bottom: 44px; }
        .p2-hero-eyebrow { font-family: 'DM Mono', monospace; font-size: 10px; letter-spacing: 0.2em; text-transform: uppercase; color: #6e9ec8; margin-bottom: 12px; }
        .p2-hero-title { font-family: 'Playfair Display', serif; font-size: 48px; font-weight: 700; color: #f0e8d8; letter-spacing: -0.03em; line-height: 1.1; margin-bottom: 12px; }
        .p2-hero-sub { font-size: 15px; color: #6a6268; font-weight: 300; max-width: 480px; line-height: 1.6; }

        /* Error */
        .p2-error-banner { background: rgba(208,128,128,0.1); border-left: 4px solid #D08080; padding: 16px 20px; border-radius: 4px; margin-bottom: 24px; display: flex; gap: 12px; }

        /* Run box */
        .p2-run-box { background: #111113; border: 1px solid #1e1e22; border-radius: 12px; padding: 32px; margin-bottom: 32px; }
        .p2-run-lede { color: #6a6268; font-size: 14px; line-height: 1.6; margin-bottom: 20px; }
        .p2-run-btn { background: linear-gradient(135deg, #6e9ec8 0%, #5a8ab8 100%); color: #fff; border: none; border-radius: 8px; padding: 16px 32px; font-family: 'DM Sans', sans-serif; font-size: 15px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 12px; transition: all 0.3s; box-shadow: 0 4px 12px rgba(110,158,200,0.25); width: 100%; justify-content: center; }
        .p2-run-btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(110,158,200,0.35); }
        .p2-run-btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        .p2-spinner { width: 18px; height: 18px; border: 2px solid rgba(255,255,255,0.25); border-radius: 50%; border-top-color: #fff; animation: spin 0.8s linear infinite; }

        /* Section header */
        .p2-section-hd { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #1a1a20; }
        .p2-section-num { font-family: 'DM Mono', monospace; font-size: 10px; color: #6e9ec8; opacity: 0.6; }
        .p2-section-title { font-family: 'Playfair Display', serif; font-size: 20px; font-weight: 600; color: #d8d0c0; flex: 1; }

        /* Processing view */
        .p2-gen-box { background: #111113; border: 1px solid #1e1e22; border-radius: 12px; padding: 28px 32px; margin-bottom: 32px; }
        .p2-gen-title { font-family: 'Playfair Display', serif; font-size: 18px; color: #f0e8d8; margin-bottom: 6px; display: flex; align-items: center; gap: 10px; }
        .p2-gen-sub { font-size: 13px; color: #6a6268; margin-bottom: 20px; }
        .p2-gen-strip { display: flex; background: #0e0e10; border: 1px solid #1e1e22; border-radius: 8px; overflow: hidden; }
        .p2-gen-step { flex: 1; padding: 14px 8px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 6px; color: #4a4a55; border-right: 1px solid #1e1e22; transition: all 0.4s; }
        .p2-gen-step:last-child { border-right: none; }
        .p2-gen-step.gs-done { color: #4a9e6f; background: rgba(74,158,111,0.07); }
        .p2-gen-step.gs-active { color: #6e9ec8; background: rgba(110,158,200,0.08); font-weight: 600; }
        .p2-gen-step-icon { font-size: 18px; }
        .p2-gen-step-label { font-size: 11px; }
        .p2-gen-step-status { font-family: 'DM Mono', monospace; font-size: 9px; letter-spacing: 0.1em; margin-top: 2px; }
        .gs-done .p2-gen-step-status { color: #4a9e6f; }
        .gs-active .p2-gen-step-status { color: #6e9ec8; animation: pulse 2s infinite; }


        /* Accordion */
        .p2-accordion { display: flex; flex-direction: column; gap: 10px; margin-bottom: 40px; }

        .p2-acc { background: #111113; border: 1px solid #1e1e22; border-radius: 12px; overflow: hidden; transition: border-color 0.2s; }
        .p2-acc:hover { border-color: #2a2a30; }

        .p2-acc-hd { width: 100%; background: none; border: none; cursor: pointer; display: flex; align-items: center; justify-content: space-between; padding: 18px 20px; gap: 16px; text-align: left; transition: background 0.15s; }
        .p2-acc-hd:hover { background: rgba(255,255,255,0.02); }
        .p2-acc-hd--open { background: rgba(110,158,200,0.04); border-bottom: 1px solid #1e1e22; }

        .p2-acc-left { display: flex; align-items: center; gap: 14px; }
        .p2-acc-icon { font-size: 20px; }
        .p2-acc-title { font-family: 'Playfair Display', serif; font-size: 16px; font-weight: 600; color: #d8d0c0; }
        .p2-acc-loc { font-size: 12px; color: #5a5a65; font-style: italic; margin-top: 2px; }

        .p2-acc-right { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
        .p2-acc-badge { font-family: 'DM Mono', monospace; font-size: 10px; letter-spacing: 0.08em; padding: 3px 10px; border-radius: 4px; }
        .p2-acc-badge--ok { background: rgba(74,158,111,0.12); color: #4a9e6f; border: 1px solid rgba(74,158,111,0.2); }
        .p2-acc-badge--err { background: rgba(208,128,128,0.12); color: #D08080; border: 1px solid rgba(208,128,128,0.2); }
        .p2-acc-badge--loading { background: rgba(110,158,200,0.12); color: #6e9ec8; border: 1px solid rgba(110,158,200,0.25); animation: pulse 1.5s infinite; }
        .p2-acc-chevron { font-size: 10px; color: #4a4a55; }
        .p2-regen-loading { padding: 28px 20px; display: flex; align-items: center; justify-content: center; gap: 12px; color: #6e9ec8; font-size: 13px; font-family: 'DM Mono', monospace; letter-spacing: 0.05em; }

        /* Accordion body */
        .p2-acc-body { padding: 20px; display: flex; flex-direction: column; gap: 18px; }

        /* Video player */
        .p2-video-wrap { background: #000; border-radius: 8px; overflow: hidden; border: 1px solid #1e1e22; }
        .p2-video { width: 100%; max-height: 480px; display: block; }
        .p2-no-video { padding: 24px; text-align: center; color: #4a4a55; font-size: 13px; font-family: 'DM Mono', monospace; background: #0e0e10; border-radius: 8px; border: 1px dashed #1e1e22; }
        .p2-scene-error { padding: 16px 18px; color: #D08080; font-size: 13px; background: rgba(208,128,128,0.08); border-radius: 8px; border: 1px solid rgba(208,128,128,0.15); }

        /* Script inside accordion */
        .p2-scene-script { background: #0d0d0f; border: 1px solid #1e1e22; border-radius: 8px; overflow: hidden; }
        .p2-scene-script-lbl { font-family: 'DM Mono', monospace; font-size: 9px; letter-spacing: 0.15em; text-transform: uppercase; color: #4a4a55; padding: 8px 14px; background: #141418; border-bottom: 1px solid #1e1e22; }
        .p2-script-line { display: flex; gap: 12px; padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,0.03); }
        .p2-script-line:last-child { border-bottom: none; }
        .p2-script-spk { font-family: 'DM Mono', monospace; font-size: 10px; color: #6e9ec8; text-transform: uppercase; min-width: 110px; flex-shrink: 0; padding-top: 2px; }
        .p2-script-body { flex: 1; }
        .p2-script-txt { font-family: 'Playfair Display', serif; font-size: 13px; font-style: italic; color: #b8b0a0; line-height: 1.5; }
        .p2-script-cue { display: flex; align-items: flex-start; gap: 6px; margin-top: 5px; padding: 4px 8px; background: rgba(110,158,200,0.05); border-left: 2px solid rgba(110,158,200,0.2); border-radius: 0 4px 4px 0; }
        .p2-script-cue-txt { font-size: 11px; color: #6a7888; }

        /* CTA bar */
        .p2-cta-bar { padding-top: 32px; border-top: 1px solid #1a1a20; display: flex; align-items: center; justify-content: space-between; }
        .p2-cta-hint { font-size: 12px; color: #3a3a44; font-family: 'DM Mono', monospace; }
        .p2-btn-back { background: transparent; color: #9a9288; border: 1px solid #2a2a30; border-radius: 7px; padding: 11px 24px; font-family: 'DM Sans', sans-serif; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.15s; }
        .p2-btn-back:hover { border-color: #3a3a40; color: #c8c0b0; }
        .p2-btn-regen { background: linear-gradient(135deg, #6e9ec8 0%, #5a8ab8 100%); color: #fff; border: none; border-radius: 7px; padding: 11px 24px; font-family: 'DM Sans', sans-serif; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
        .p2-btn-regen:hover:not(:disabled) { transform: translateY(-1px); }
        .p2-btn-regen:disabled { opacity: 0.6; cursor: not-allowed; }
      `}</style>

      <div className="p2-root">
        {/* Sidebar */}
        <aside className="p2-sidebar">
          <div 
            className="p2-logo" 
            onClick={() => { if (!loading) navigate('/'); }}
            style={{ cursor: !loading ? 'pointer' : 'default' }}
          >
            <div className="p2-logo-eyebrow">Studio Floor</div>
            <div className="p2-logo-title">Montage</div>
          </div>
          <div className="p2-nav-sec">
            <div className="p2-sec-lbl">Production Agents</div>
            {agents.map(a => (
              <div key={a.name} className="p2-agent-row">
                <span className="p2-agent-icon">{a.icon}</span>
                <span className="p2-agent-name">{a.name}</span>
                <span className={`p2-agent-dot ${loading ? 'running' : phase2Done ? 'done' : 'idle'}`} />
              </div>
            ))}
          </div>
          <div className="p2-sidebar-footer">CS-4015 Agentic AI · FAST NUCES</div>
        </aside>

        {/* Script Sidebar Right */}
        <div className={`p2-script-side ${sidebarOpen ? 'p2-script-side--open' : ''}`}>
          <div className="p2-script-side-hd">
            <div className="p2-script-side-title">Phase 1 Script</div>
            <button className="p2-script-side-close" onClick={() => setSidebarOpen(false)}>✕</button>
          </div>
          <div className="p2-script-side-body">
            {refScript?.scenes.map(s => (
              <div key={s.scene_id} className="p2-script-side-scene">
                <div className="p2-side-scene-id">SCENE {s.scene_id}</div>
                <div className="p2-side-scene-loc">{s.location}</div>
                {s.dialogue.map((d, idx) => (
                  <div key={idx} style={{ marginBottom: '8px', fontSize: '13px' }}>
                    <span style={{ color: '#6e9ec8', fontWeight: 600, marginRight: '6px' }}>{d.speaker}:</span>
                    <span style={{ fontStyle: 'italic', color: '#b8b0a0' }}>"{d.line}"</span>
                  </div>
                ))}
              </div>
            ))}
            {!refScript && <div className="p2-no-video">No script loaded.</div>}
          </div>
        </div>

        <button className="p2-script-toggle" onClick={() => setSidebarOpen(true)} title="View Script">
          📜
        </button>

        {/* Main */}
        <main className="p2-main">
          <div className="p2-topbar">
            <div className="p2-breadcrumb">Montage <span>/</span> Phase 2 — Studio Floor</div>
            <div className="p2-phase-badge">Phase 2 of 2</div>
          </div>

          <div className="p2-content">
            <div className="p2-hero">
              <div className="p2-hero-eyebrow">Phase 2 · Studio Floor</div>
              <h1 className="p2-hero-title">Video Production &amp;<br />Post-Processing</h1>
              <p className="p2-hero-sub">AI-generated video, synthesized dialogue, face replacement, and lip synchronisation.</p>
            </div>

            {error && (
              <div className="p2-error-banner">
                <span>⚠️</span>
                <div><strong>Error</strong><br />{error}</div>
              </div>
            )}

            {/* ── Run button (idle, not yet done) ── */}
            {!phase2Done && !loading && (
              <div className="p2-run-box">
                <div className="p2-run-lede">
                  Generate fresh video for each scene from the current Phase 1 script and character designs.
                  Previous runs are not shown automatically — use &quot;Load saved outputs&quot; only if you want files already on disk.
                </div>
                <button className="p2-run-btn" onClick={() => handleRun()}>
                  🎬 Run Phase 2
                </button>
                <button
                  type="button"
                  className="p2-btn-back"
                  style={{ marginTop: '14px', width: '100%', justifyContent: 'center' }}
                  onClick={() => void loadOutputsFromDisk()}
                >
                  Load saved outputs from disk
                </button>
              </div>
            )}

            {/* ── Full-pipeline processing view (only for whole runs, not single-scene regen) ── */}
            {loading && !regeneratingSceneId && (() => {
              const steps = [
                { icon: '🎬', label: 'Video Gen' },
                { icon: '🎤', label: 'Voice Synth' },
                { icon: '👤', label: 'Face Swap' },
                { icon: '🔊', label: 'Lip Sync' },
              ];
              return (
                <div className="p2-gen-box">
                  <div className="p2-gen-title">
                    <div className="p2-spinner" />
                    Generating Videos…
                  </div>
                  <div className="p2-gen-sub">Running the full production pipeline. This may take a few minutes.</div>
                  <div className="p2-gen-strip">
                    {steps.map((s, i) => {
                      const cls = i < loadingStepIdx ? 'gs-done' : i === loadingStepIdx ? 'gs-active' : '';
                      return (
                        <div key={s.label} className={`p2-gen-step ${cls}`}>
                          <span className="p2-gen-step-icon">{s.icon}</span>
                          <span className="p2-gen-step-label">{s.label}</span>
                          <span className="p2-gen-step-status">
                            {i < loadingStepIdx ? '✓ DONE' : i === loadingStepIdx ? 'RUNNING…' : 'PENDING'}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()}

            {/* ── Scene accordion — visible when done, or during single-scene regen ── */}
            {(phase2Done || regeneratingSceneId !== null) && displayScenes.length > 0 && !(loading && !regeneratingSceneId) && (
              <>
                <div className="p2-section-hd">
                  <span className="p2-section-num">01</span>
                  <span className="p2-section-title">Generated Scenes</span>
                </div>
                <div className="p2-accordion">
                  {displayScenes.map(result => (
                    <SceneAccordion
                      key={result.scene_id}
                      result={result}
                      refScene={getRefScene(result.scene_id)}
                      videoNonce={runNonce}
                      onRegen={(sid) => handleRun(sid)}
                      isRegenerating={regeneratingSceneId === result.scene_id}
                    />
                  ))}
                </div>
              </>
            )}

            <div className="p2-cta-bar">
              <div className="p2-cta-hint">← Writers' Room</div>
              <div style={{ display: 'flex', gap: '12px' }}>
                <button className="p2-btn-back" onClick={() => navigate('/')} disabled={loading}>
                  {loading ? 'Production Running...' : '← Back to Phase 1'}
                </button>
                {phase2Done && (
                  <button className="p2-btn-regen" onClick={() => handleRun()} disabled={loading}>
                    {loading ? 'Running…' : 'Regenerate'}
                  </button>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    </>
  );
};

export default Phase2;