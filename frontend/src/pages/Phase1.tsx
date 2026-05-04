import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import HITLModal from './HITLModal';

const Phase1 = () => {
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [postApprovalStepIdx, setPostApprovalStepIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [phase1Output, setPhase1Output] = useState<any>(null);
  const [hitlPending, setHitlPending] = useState(false);
  const [pendingScript, setPendingScript] = useState<any>(null);

  useEffect(() => {
    if (!isProcessing) { setCurrentStepIndex(0); return; }
    const t = setInterval(() => setCurrentStepIndex(p => p < 3 ? p + 1 : p), 10000);
    return () => clearInterval(t);
  }, [isProcessing]);

  useEffect(() => {
    if (!isApproving) { setPostApprovalStepIdx(0); return; }
    const t = setInterval(() => setPostApprovalStepIdx(p => p < 1 ? p + 1 : p), 8000);
    return () => clearInterval(t);
  }, [isApproving]);

  const handleProcess = async () => {
    setIsProcessing(true);
    setError(null);
    setPhase1Output(null);
    setHitlPending(false);
    setPendingScript(null);
    try {
      const res = await fetch('http://localhost:8000/api/phase1/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || 'Pipeline failed');
      if (data.data?.error) throw new Error(data.data.error);
      if (data.data?.status === 'awaiting_hitl') {
        setHitlPending(true);
        setPendingScript(data.data.script);
      } else {
        setPhase1Output(data.data);
      }
    } catch (err: any) {
      setError(err.message || 'An unknown error occurred');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleHITL = async (approved: boolean) => {
    // Close modal immediately
    setHitlPending(false);
    setPendingScript(null);
    if (!approved) {
      setError('Script rejected. Adjust your prompt and try again.');
      return;
    }
    setIsApproving(true);
    try {
      const res = await fetch('http://localhost:8000/api/phase1/hitl/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || 'HITL request failed');
      if (data.data?.error) throw new Error(data.data.error);
      setPhase1Output(data.data);
    } catch (err: any) {
      setError(err.message || 'An unknown error occurred');
    } finally {
      setIsApproving(false);
    }
  };

  const promptExample = "Example: A detective interrogates a suspect in a dimly-lit room.";

  const sidebarAgents = [
    { icon: '✍️', name: 'Scriptwriter' },
    { icon: '🎨', name: 'Character Designer' },
    { icon: '🖼️', name: 'Image Synthesis' },
    { icon: '✅', name: 'Validator' },
  ];

  const getAgentStatus = (i: number) => {
    if (phase1Output) return 'done';
    if (!isProcessing) return 'idle';
    if (i < currentStepIndex) return 'done';
    if (i === currentStepIndex) return 'running';
    return 'idle';
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=DM+Sans:wght@300;400;500&family=DM+Mono:wght@400&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        .pm-root { display: flex; min-height: 100vh; background: #0a0a0b; color: #e8e0d0; font-family: 'DM Sans', sans-serif; font-size: 14px; }

        /* SIDEBAR */
        .pm-sidebar { width: 240px; min-width: 240px; position: fixed; top: 0; left: 0; bottom: 0; background: #111113; border-right: 1px solid #1e1e22; display: flex; flex-direction: column; padding: 28px 0 24px; z-index: 100; }
        .pm-logo { padding: 0 24px 28px; border-bottom: 1px solid #1e1e22; }
        .pm-logo-eyebrow { font-family: 'DM Mono', monospace; font-size: 9px; letter-spacing: 0.2em; text-transform: uppercase; color: #c8a96e; margin-bottom: 4px; }
        .pm-logo-title { font-family: 'Playfair Display', serif; font-size: 20px; font-weight: 700; color: #f0e8d8; letter-spacing: -0.02em; }
        .pm-nav-section { padding: 20px 24px 16px; border-bottom: 1px solid #1e1e22; }
        .pm-nav-section-label { font-size: 9px; letter-spacing: 0.15em; text-transform: uppercase; color: #4a4a55; font-weight: 500; margin-bottom: 12px; }
        .pm-agent-row { display: flex; align-items: center; gap: 10px; padding: 7px 0; }
        .pm-agent-icon { font-size: 13px; width: 20px; text-align: center; }
        .pm-agent-name { flex: 1; font-size: 13px; color: #b0a898; }
        .pm-agent-status { width: 6px; height: 6px; border-radius: 50%; background: #2a2a30; }
        .pm-agent-status.done { background: #4a9e6f; }
        .pm-agent-status.running { background: #c8a96e; box-shadow: 0 0 0 3px rgba(200,169,110,0.15); animation: pulse 2s infinite; }
        .pm-agent-status.idle { background: #4a4a55; }
        @keyframes pulse { 0%,100%{ opacity:1; } 50%{ opacity:0.5; } }
        @keyframes spin { to { transform: rotate(360deg); } }
        .pm-mem-block { padding: 20px 24px; border-bottom: 1px solid #1e1e22; }
        .pm-mem-chip { display: flex; align-items: center; gap: 8px; background: #181820; border: 1px solid #1e1e22; border-radius: 6px; padding: 8px 12px; font-family: 'DM Mono', monospace; font-size: 11px; color: #6e9ec8; }
        .pm-sidebar-footer { margin-top: auto; padding: 16px 24px 0; border-top: 1px solid #1e1e22; font-size: 10px; color: #3a3a44; font-family: 'DM Mono', monospace; letter-spacing: 0.05em; }

        /* MAIN */
        .pm-main { margin-left: 240px; flex: 1; display: flex; flex-direction: column; min-height: 100vh; }
        .pm-topbar { position: sticky; top: 0; z-index: 50; background: rgba(10,10,11,0.92); backdrop-filter: blur(8px); border-bottom: 1px solid #1e1e22; padding: 0 40px; height: 52px; display: flex; align-items: center; justify-content: space-between; }
        .pm-breadcrumb { font-family: 'DM Mono', monospace; font-size: 11px; color: #4a4a55; display: flex; align-items: center; gap: 8px; }
        .pm-breadcrumb span { color: #c8a96e; }
        .pm-phase-badge { font-family: 'DM Mono', monospace; font-size: 10px; letter-spacing: 0.12em; background: rgba(200,169,110,0.12); color: #c8a96e; border: 1px solid rgba(200,169,110,0.25); border-radius: 4px; padding: 4px 10px; text-transform: uppercase; }
        .pm-content { padding: 48px 40px 80px; max-width: 880px; }

        /* HERO */
        .pm-hero { margin-bottom: 52px; }
        .pm-hero-eyebrow { font-family: 'DM Mono', monospace; font-size: 10px; letter-spacing: 0.2em; text-transform: uppercase; color: #c8a96e; margin-bottom: 12px; }
        .pm-hero-title { font-family: 'Playfair Display', serif; font-size: 48px; font-weight: 700; color: #f0e8d8; letter-spacing: -0.03em; line-height: 1.1; margin-bottom: 12px; }
        .pm-hero-sub { font-size: 15px; color: #6a6268; font-weight: 300; max-width: 480px; line-height: 1.6; }

        /* ERROR */
        .pm-error-banner { background: rgba(208,128,128,0.1); border-left: 4px solid #D08080; color: #e8e0d0; padding: 16px 20px; border-radius: 4px; margin-bottom: 24px; display: flex; align-items: flex-start; gap: 12px; font-size: 14px; }

        /* PIPELINE STRIP */
        .pm-pipeline-strip { display: flex; background: #111113; border: 1px solid #1e1e22; border-radius: 8px; margin-bottom: 24px; overflow: hidden; }
        .pm-strip-step { flex: 1; padding: 12px 8px; text-align: center; font-size: 11px; color: #4a4a55; border-right: 1px solid #1e1e22; display: flex; flex-direction: column; align-items: center; gap: 6px; transition: all 0.3s; }
        .pm-strip-step:last-child { border-right: none; }
        .pm-strip-step.active { color: #c8a96e; background: rgba(200,169,110,0.08); font-weight: 600; }
        .pm-strip-step.done { color: #4a9e6f; background: rgba(74,158,111,0.08); }
        .pm-strip-icon { font-size: 16px; }

        /* PROMPT BOX */
        .pm-prompt-container { background: #111113; border: 1px solid #1e1e22; border-radius: 12px; padding: 32px; margin-bottom: 32px; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
        .pm-prompt-label { font-family: 'DM Mono', monospace; font-size: 12px; letter-spacing: 0.1em; color: #c8a96e; margin-bottom: 16px; text-transform: uppercase; display: flex; align-items: center; gap: 8px; }
        .pm-prompt-textarea { width: 100%; min-height: 160px; background: #181820; border: 1px solid #2a2a30; border-radius: 8px; padding: 20px; color: #e8e0d0; font-family: 'DM Sans', sans-serif; font-size: 16px; line-height: 1.6; resize: vertical; transition: all 0.3s; }
        .pm-prompt-textarea:focus { outline: none; border-color: #c8a96e; background: #1c1c24; box-shadow: 0 0 0 2px rgba(200,169,110,0.1); }
        .pm-prompt-textarea::placeholder { color: #4a4a55; }
        .pm-prompt-example { margin-top: 12px; font-size: 13px; color: #6a6268; font-style: italic; display: flex; align-items: center; gap: 6px; }
        .pm-process-btn { margin-top: 24px; background: linear-gradient(135deg, #c8a96e 0%, #b5955b 100%); color: #0a0a0b; border: none; border-radius: 8px; padding: 16px 32px; font-family: 'DM Sans', sans-serif; font-size: 15px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 12px; transition: all 0.3s cubic-bezier(0.4,0,0.2,1); box-shadow: 0 4px 12px rgba(200,169,110,0.2); width: 100%; }
        .pm-process-btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(200,169,110,0.3); background: linear-gradient(135deg, #d4b87a 0%, #c8a96e 100%); }
        .pm-process-btn:disabled { opacity: 0.6; cursor: not-allowed; background: #2a2a30; color: #8a8880; box-shadow: none; }
        .pm-spinner { width: 18px; height: 18px; border: 2px solid rgba(10,10,11,0.25); border-radius: 50%; border-top-color: #0a0a0b; animation: spin 0.8s linear infinite; flex-shrink: 0; }

        /* CTA */
        .pm-cta-bar { margin-top: 16px; padding-top: 32px; border-top: 1px solid #1a1a20; display: flex; align-items: center; justify-content: space-between; }
        .pm-cta-hint { font-size: 12px; color: #3a3a44; font-family: 'DM Mono', monospace; }
        .pm-btn-primary { background: #c8a96e; color: #0a0a0b; border: none; border-radius: 7px; padding: 11px 24px; font-family: 'DM Sans', sans-serif; font-size: 13px; font-weight: 500; cursor: pointer; display: flex; align-items: center; gap: 8px; letter-spacing: 0.02em; transition: background 0.15s, transform 0.1s; }
        .pm-btn-primary:hover { background: #d4b87a; transform: translateY(-1px); }

        /* POST-APPROVAL PROCESSING */
        .pm-approving-box { background: #111113; border: 1px solid #1e1e22; border-radius: 12px; padding: 28px 32px; margin-bottom: 28px; }
        .pm-approving-title { font-family: 'Playfair Display', serif; font-size: 18px; color: #f0e8d8; margin-bottom: 6px; display: flex; align-items: center; gap: 10px; }
        .pm-approving-sub { font-size: 13px; color: #6a6268; margin-bottom: 20px; }
        .pm-post-steps { display: flex; gap: 0; background: #0e0e10; border: 1px solid #1e1e22; border-radius: 8px; overflow: hidden; }
        .pm-post-step { flex: 1; padding: 14px 12px; text-align: center; font-size: 12px; color: #4a4a55; border-right: 1px solid #1e1e22; display: flex; flex-direction: column; align-items: center; gap: 6px; transition: all 0.4s; }
        .pm-post-step:last-child { border-right: none; }
        .pm-post-step.ps-done { color: #4a9e6f; background: rgba(74,158,111,0.07); }
        .pm-post-step.ps-active { color: #c8a96e; background: rgba(200,169,110,0.08); font-weight: 600; }
        .pm-post-step-icon { font-size: 18px; }
        .pm-post-step-label { font-size: 11px; }
        .pm-post-step-status { font-family: 'DM Mono', monospace; font-size: 9px; letter-spacing: 0.1em; margin-top: 2px; }
        .ps-done .pm-post-step-status { color: #4a9e6f; }
        .ps-active .pm-post-step-status { color: #c8a96e; animation: pulse 2s infinite; }

        /* RESULTS SECTION */
        .pm-results-section { margin-bottom: 40px; }
        .pm-results-hd { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; padding-bottom: 12px; border-bottom: 1px solid #1a1a20; }
        .pm-results-num { font-family: 'DM Mono', monospace; font-size: 10px; color: #c8a96e; opacity: 0.6; }
        .pm-results-title { font-family: 'Playfair Display', serif; font-size: 20px; font-weight: 600; color: #d8d0c0; flex: 1; }

        /* Script display */
        .pm-script-scene { background: #111113; border: 1px solid #1e1e22; border-radius: 10px; margin-bottom: 12px; overflow: hidden; }
        .pm-script-scene-hd { display: flex; align-items: center; gap: 14px; padding: 10px 18px; background: #141418; border-bottom: 1px solid #1e1e22; }
        .pm-script-scene-id { font-family: 'DM Mono', monospace; font-size: 10px; color: #c8a96e; letter-spacing: 0.1em; }
        .pm-script-scene-loc { font-size: 12px; color: #5a5a65; font-style: italic; }
        .pm-script-line { display: flex; gap: 14px; padding: 11px 18px; border-bottom: 1px solid rgba(255,255,255,0.03); }
        .pm-script-line:last-child { border-bottom: none; }
        .pm-script-spk { font-family: 'DM Mono', monospace; font-size: 10px; color: #c8a96e; text-transform: uppercase; min-width: 110px; flex-shrink: 0; padding-top: 2px; }
        .pm-script-body { flex: 1; }
        .pm-script-txt { font-family: 'Playfair Display', serif; font-size: 14px; font-style: italic; color: #c8c0b0; line-height: 1.55; }
        .pm-script-cue { display: flex; align-items: flex-start; gap: 6px; margin-top: 6px; padding: 5px 10px; background: rgba(200,169,110,0.05); border-left: 2px solid rgba(200,169,110,0.2); border-radius: 0 4px 4px 0; }
        .pm-script-cue-txt { font-size: 12px; color: #7a7268; line-height: 1.4; }

        /* Character grid */
        .pm-char-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }
        .pm-char-card { background: #111113; border: 1px solid #1e1e22; border-radius: 12px; overflow: hidden; transition: border-color 0.2s; }
        .pm-char-card:hover { border-color: #2a2a30; }
        .pm-char-img-wrap { height: 200px; background: #0e0e10; display: flex; align-items: center; justify-content: center; overflow: hidden; }
        .pm-char-img { width: 100%; height: 100%; object-fit: cover; }
        .pm-char-no-img { font-size: 48px; opacity: 0.2; }
        .pm-char-body { padding: 16px; }
        .pm-char-name { font-family: 'Playfair Display', serif; font-size: 16px; font-weight: 600; color: #f0e8d8; margin-bottom: 8px; }
        .pm-char-desc { font-size: 13px; color: #7a7268; line-height: 1.5; margin-bottom: 10px; }
        .pm-char-style { font-family: 'DM Mono', monospace; font-size: 10px; color: #6e9ec8; margin-bottom: 10px; }
        .pm-char-tags { display: flex; flex-wrap: wrap; gap: 5px; }
        .pm-char-tag { font-size: 10px; font-family: 'DM Mono', monospace; padding: 2px 8px; border-radius: 4px; background: rgba(200,169,110,0.1); color: #c8a96e; border: 1px solid rgba(200,169,110,0.2); }


        /* ── HITL MODAL ── */
        .pm-hitl-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(6px); z-index: 200; display: flex; align-items: center; justify-content: center; padding: 24px 20px; }
        .pm-hitl-modal { background: #111113; border: 1px solid #2a2a30; border-radius: 16px; width: 100%; max-width: 780px; max-height: 90vh; display: flex; flex-direction: column; box-shadow: 0 24px 80px rgba(0,0,0,0.7); overflow: hidden; }
        .pm-hitl-header { flex-shrink: 0; padding: 24px 32px 20px; border-bottom: 1px solid #1e1e22; }
        .pm-hitl-badge { font-family: 'DM Mono', monospace; font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: #c8a96e; margin-bottom: 10px; }
        .pm-hitl-title { font-family: 'Playfair Display', serif; font-size: 26px; font-weight: 700; color: #f0e8d8; margin-bottom: 8px; }
        .pm-hitl-sub { font-size: 13px; color: #6a6268; line-height: 1.6; }
        .pm-hitl-body { flex: 1; min-height: 0; overflow-y: scroll; padding: 20px 32px 28px; display: flex; flex-direction: column; gap: 14px; }
        .pm-hitl-body::-webkit-scrollbar { width: 6px; }
        .pm-hitl-body::-webkit-scrollbar-track { background: #0e0e10; }
        .pm-hitl-body::-webkit-scrollbar-thumb { background: #3a3a44; border-radius: 6px; }
        .pm-hitl-body::-webkit-scrollbar-thumb:hover { background: #5a5a65; }

        /* Scene cards inside modal */
        .pm-scene { background: #0e0e10; border: 1px solid #1e1e22; border-radius: 10px; overflow: hidden; }
        .pm-scene-head { display: flex; align-items: center; gap: 14px; padding: 10px 16px; background: #141418; border-bottom: 1px solid #1e1e22; }
        .pm-scene-id { font-family: 'DM Mono', monospace; font-size: 10px; color: #c8a96e; letter-spacing: 0.1em; }
        .pm-scene-loc { font-size: 12px; color: #6a6268; font-style: italic; }
        .pm-line { display: flex; gap: 14px; padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,0.03); align-items: flex-start; }
        .pm-line:last-child { border-bottom: none; }
        .pm-line-spk { font-family: 'DM Mono', monospace; font-size: 10px; letter-spacing: 0.08em; color: #c8a96e; min-width: 90px; padding-top: 2px; text-transform: uppercase; }
        .pm-line-body { flex: 1; }
        .pm-line-txt { font-size: 14px; color: #c8c0b0; line-height: 1.55; font-style: italic; font-family: 'Playfair Display', serif; }
        .pm-line-cue { display: flex; align-items: flex-start; gap: 6px; margin-top: 7px; background: rgba(200,169,110,0.06); border-left: 2px solid rgba(200,169,110,0.25); padding: 5px 10px; border-radius: 0 4px 4px 0; }
        .pm-line-cue-icon { font-size: 11px; color: #c8a96e; opacity: 0.7; flex-shrink: 0; margin-top: 1px; }
        .pm-line-cue-text { font-size: 12px; color: #8a8070; font-family: 'DM Sans', sans-serif; font-style: normal; line-height: 1.4; }

        /* HITL action buttons row — inside the header */
        .pm-hitl-actions { display: flex; gap: 12px; margin-top: 16px; }
        .pm-btn-reject { background: transparent; color: #9a8880; border: 1px solid #2a2a30; border-radius: 7px; padding: 10px 20px; font-family: 'DM Sans', sans-serif; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.15s; }
        .pm-btn-reject:hover:not(:disabled) { border-color: #D08080; color: #D08080; }
        .pm-btn-reject:disabled { opacity: 0.5; cursor: not-allowed; }
        .pm-btn-approve { background: linear-gradient(135deg, #4a9e6f 0%, #3a8a5e 100%); color: #fff; border: none; border-radius: 7px; padding: 10px 22px; font-family: 'DM Sans', sans-serif; font-size: 13px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: all 0.2s; box-shadow: 0 4px 12px rgba(74,158,111,0.25); }
        .pm-btn-approve:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(74,158,111,0.35); }
        .pm-btn-approve:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        .pm-spinner-white { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.25); border-radius: 50%; border-top-color: #fff; animation: spin 0.8s linear infinite; flex-shrink: 0; }
      `}</style>


      {/* ── HITL MODAL (separate component) ── */}
      {hitlPending && pendingScript && (
        <HITLModal
          script={pendingScript}
          isApproving={isApproving}
          onApprove={() => handleHITL(true)}
          onReject={() => handleHITL(false)}
        />
      )}

      <div className="pm-root">
        <aside className="pm-sidebar">
          <div className="pm-logo">
            <div className="pm-logo-eyebrow">Project</div>
            <div className="pm-logo-title">Montage</div>
          </div>
          <div className="pm-nav-section">
            <div className="pm-nav-section-label">Pipeline Agents</div>
            {sidebarAgents.map((a, i) => (
              <div key={a.name} className="pm-agent-row">
                <span className="pm-agent-icon">{a.icon}</span>
                <span className="pm-agent-name">{a.name}</span>
                <span className={`pm-agent-status ${getAgentStatus(i)}`} />
              </div>
            ))}
          </div>
          <div className="pm-mem-block">
            <div className="pm-nav-section-label">Memory Layer</div>
            <div className="pm-mem-chip"><span>🗄</span><span>ChromaDB vector store</span></div>
          </div>
          <div className="pm-sidebar-footer">CS-4015 Agentic AI · FAST NUCES</div>
        </aside>

        <main className="pm-main">
          <div className="pm-topbar">
            <div className="pm-breadcrumb">Montage <span>/</span> Phase 1 — Writers' Room</div>
            <div className="pm-phase-badge">Phase 1 of 2</div>
          </div>

          <div className="pm-content">
            <div className="pm-hero">
              <div className="pm-hero-eyebrow">Phase 1 · Writers' Room</div>
              <h1 className="pm-hero-title">Scriptwriting &amp;<br />Character Design</h1>
              <p className="pm-hero-sub">AI-powered screenplay generation and character creation for film production.</p>
            </div>

            {error && (
              <div className="pm-error-banner">
                <span>⚠️</span>
                <div><strong>Pipeline Error</strong><br />{error}</div>
              </div>
            )}

            {/* ── Scriptwriting in progress ── */}
            {isProcessing && (
              <div className="pm-pipeline-strip">
                {sidebarAgents.map((step, idx) => {
                  let cls = '';
                  if (idx < currentStepIndex) cls = 'done';
                  else if (idx === currentStepIndex) cls = 'active';
                  return (
                    <div key={step.name} className={`pm-strip-step ${cls}`}>
                      <span className="pm-strip-icon">{step.icon}</span>
                      <span>{step.name}</span>
                    </div>
                  );
                })}
              </div>
            )}

            {/* ── Post-approval processing ── */}
            {isApproving && (
              <div className="pm-approving-box">
                <div className="pm-approving-title">
                  <div className="pm-spinner" style={{borderTopColor:'#c8a96e', borderColor:'rgba(200,169,110,0.25)'}} />
                  Generating Characters &amp; Images…
                </div>
                <div className="pm-approving-sub">Script approved. Running character design and image synthesis pipeline.</div>
                <div className="pm-post-steps">
                  {[{icon:'🎨',label:'Character Designer'},{icon:'🖼️',label:'Image Synthesis'}].map((s,i) => {
                    const cls = i < postApprovalStepIdx ? 'ps-done' : i === postApprovalStepIdx ? 'ps-active' : '';
                    return (
                      <div key={s.label} className={`pm-post-step ${cls}`}>
                        <span className="pm-post-step-icon">{s.icon}</span>
                        <span className="pm-post-step-label">{s.label}</span>
                        <span className="pm-post-step-status">
                          {i < postApprovalStepIdx ? '✓ DONE' : i === postApprovalStepIdx ? 'RUNNING…' : 'PENDING'}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ── Prompt box (only when fully idle) ── */}
            {!isProcessing && !isApproving && !phase1Output && (
              <div className="pm-prompt-container">
                <label className="pm-prompt-label"><span>⚡</span> Story Prompt</label>
                <textarea
                  className="pm-prompt-textarea"
                  placeholder="Describe your scene or story concept..."
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                />
                <div className="pm-prompt-example"><span>💡</span>{promptExample}</div>
                <button
                  className="pm-process-btn"
                  onClick={handleProcess}
                  disabled={!prompt.trim()}
                >
                  Generate Script &amp; Characters ✨
                </button>
              </div>
            )}

            {/* ── Full results (hidden during re-generation) ── */}
            {phase1Output && !error && !isProcessing && (
              <>
                {/* Script */}
                {phase1Output.script?.scenes?.length > 0 && (
                  <div className="pm-results-section">
                    <div className="pm-results-hd">
                      <span className="pm-results-num">01</span>
                      <span className="pm-results-title">Generated Script</span>
                    </div>
                    {phase1Output.script.scenes.map((scene: any) => (
                      <div key={scene.scene_id} className="pm-script-scene">
                        <div className="pm-script-scene-hd">
                          <span className="pm-script-scene-id">SCENE {scene.scene_id}</span>
                          <span className="pm-script-scene-loc">{scene.location}</span>
                        </div>
                        {scene.dialogue?.map((d: any, i: number) => (
                          <div key={i} className="pm-script-line">
                            <div className="pm-script-spk">{d.speaker}</div>
                            <div className="pm-script-body">
                              <div className="pm-script-txt">"{d.line}"</div>
                              {d.visual_cue && (
                                <div className="pm-script-cue">
                                  <span>🎥</span>
                                  <span className="pm-script-cue-txt">{d.visual_cue}</span>
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}

                {/* Characters */}
                {phase1Output.characters?.length > 0 && (
                  <div className="pm-results-section">
                    <div className="pm-results-hd">
                      <span className="pm-results-num">02</span>
                      <span className="pm-results-title">Characters</span>
                    </div>
                    <div className="pm-char-grid">
                      {phase1Output.characters.map((char: any) => (
                        <div key={char.name} className="pm-char-card">
                          <div className="pm-char-img-wrap">
                            {char.image_path ? (
                              <img
                                className="pm-char-img"
                                src={`http://localhost:8000/api/phase1/character-image/${encodeURIComponent(char.name)}`}
                                alt={char.name}
                                onError={(e) => { (e.target as HTMLImageElement).style.display='none'; }}
                              />
                            ) : (
                              <span className="pm-char-no-img">🎭</span>
                            )}
                          </div>
                          <div className="pm-char-body">
                            <div className="pm-char-name">{char.name}</div>
                            <div className="pm-char-desc">{char.appearance_description}</div>
                            {char.reference_style && <div className="pm-char-style">Style: {char.reference_style}</div>}
                            <div className="pm-char-tags">
                              {char.personality_traits?.map((t: string) => (
                                <span key={t} className="pm-char-tag">{t}</span>
                              ))}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="pm-cta-bar">
                  <div className="pm-cta-hint">Phase 1 complete · Ready for production</div>
                  <button className="pm-btn-primary" onClick={() => navigate('/phase2')}>
                    Proceed to Phase 2 →
                  </button>
                </div>
              </>
            )}
          </div>
        </main>
      </div>
    </>
  );
};

export default Phase1;
