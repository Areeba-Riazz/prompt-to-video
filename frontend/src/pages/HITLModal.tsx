interface DialogueLine {
  speaker: string;
  line: string;
  visual_cue?: string;
}

interface Scene {
  scene_id: number;
  location: string;
  characters: string[];
  dialogue: DialogueLine[];
}

interface Script {
  scenes: Scene[];
}

interface Props {
  script: Script;
  isApproving: boolean;
  onApprove: () => void;
  onReject: () => void;
}

const HITLModal = ({ script, isApproving, onApprove, onReject }: Props) => (
  <>
    <style>{`
      .hitl-overlay {
        position: fixed;
        inset: 0;
        z-index: 9999;
        background: rgba(0, 0, 0, 0.82);
        backdrop-filter: blur(6px);
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 24px 16px;
      }

      .hitl-modal {
        background: #111113;
        border: 1px solid #2a2a30;
        border-radius: 16px;
        width: 100%;
        max-width: 760px;
        height: 85vh;
        display: flex;
        flex-direction: column;
        box-shadow: 0 24px 80px rgba(0,0,0,0.7);
      }

      /* ── Fixed header ── */
      .hitl-header {
        flex-shrink: 0;
        padding: 22px 28px 18px;
        border-bottom: 1px solid #1e1e22;
      }

      .hitl-badge {
        font-family: 'DM Mono', monospace;
        font-size: 10px;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #c8a96e;
        margin-bottom: 8px;
      }

      .hitl-title {
        font-family: 'Playfair Display', serif;
        font-size: 24px;
        font-weight: 700;
        color: #f0e8d8;
        margin-bottom: 4px;
      }

      .hitl-sub {
        font-size: 13px;
        color: #6a6268;
        margin-bottom: 14px;
      }

      .hitl-actions {
        display: flex;
        gap: 10px;
      }

      .hitl-btn-reject {
        background: transparent;
        color: #9a8880;
        border: 1px solid #2a2a30;
        border-radius: 7px;
        padding: 9px 18px;
        font-family: 'DM Sans', sans-serif;
        font-size: 13px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.15s;
      }
      .hitl-btn-reject:hover:not(:disabled) { border-color: #D08080; color: #D08080; }
      .hitl-btn-reject:disabled { opacity: 0.45; cursor: not-allowed; }

      .hitl-btn-approve {
        background: linear-gradient(135deg, #4a9e6f 0%, #3a8a5e 100%);
        color: #fff;
        border: none;
        border-radius: 7px;
        padding: 9px 20px;
        font-family: 'DM Sans', sans-serif;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        box-shadow: 0 4px 12px rgba(74,158,111,0.25);
        transition: all 0.2s;
      }
      .hitl-btn-approve:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(74,158,111,0.35); }
      .hitl-btn-approve:disabled { opacity: 0.55; cursor: not-allowed; transform: none; }

      @keyframes hitl-spin { to { transform: rotate(360deg); } }
      .hitl-spinner {
        width: 14px;
        height: 14px;
        border: 2px solid rgba(255,255,255,0.25);
        border-radius: 50%;
        border-top-color: #fff;
        animation: hitl-spin 0.8s linear infinite;
        flex-shrink: 0;
      }

      /* ── Scrollable body ── */
      .hitl-body {
        flex: 1;
        min-height: 0;
        overflow-y: auto;
        padding: 18px 28px 24px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }

      .hitl-body::-webkit-scrollbar { width: 6px; }
      .hitl-body::-webkit-scrollbar-track { background: #0a0a0b; }
      .hitl-body::-webkit-scrollbar-thumb { background: #3a3a44; border-radius: 6px; }
      .hitl-body::-webkit-scrollbar-thumb:hover { background: #5a5a65; }

      /* ── Scene cards ── */
      .hitl-scene {
        background: #0d0d0f;
        border: 1px solid #1e1e22;
        border-radius: 10px;
      }

      .hitl-scene-head {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 9px 14px;
        background: #141418;
        border-bottom: 1px solid #1e1e22;
        border-radius: 10px 10px 0 0;
      }

      .hitl-scene-id {
        font-family: 'DM Mono', monospace;
        font-size: 10px;
        color: #c8a96e;
        letter-spacing: 0.1em;
      }

      .hitl-scene-loc {
        font-size: 12px;
        color: #5a5a65;
        font-style: italic;
      }

      /* ── Dialogue ── */
      .hitl-line {
        display: flex;
        gap: 12px;
        padding: 11px 14px;
        border-bottom: 1px solid rgba(255,255,255,0.03);
      }
      .hitl-line:last-child { border-bottom: none; }

      .hitl-speaker {
        font-family: 'DM Mono', monospace;
        font-size: 10px;
        color: #c8a96e;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        white-space: nowrap;
        min-width: 120px;
        padding-top: 2px;
        flex-shrink: 0;
      }

      .hitl-line-content { flex: 1; min-width: 0; }

      .hitl-dialogue {
        font-family: 'Playfair Display', serif;
        font-size: 14px;
        font-style: italic;
        color: #c8c0b0;
        line-height: 1.55;
      }

      .hitl-cue {
        display: flex;
        align-items: flex-start;
        gap: 7px;
        margin-top: 7px;
        padding: 5px 10px;
        background: rgba(200,169,110,0.05);
        border-left: 2px solid rgba(200,169,110,0.22);
        border-radius: 0 4px 4px 0;
      }

      .hitl-cue-icon {
        font-size: 11px;
        flex-shrink: 0;
        margin-top: 1px;
      }

      .hitl-cue-text {
        font-size: 12px;
        color: #807870;
        font-family: 'DM Sans', sans-serif;
        font-style: normal;
        line-height: 1.45;
      }
    `}</style>

    <div className="hitl-overlay">
      <div className="hitl-modal">

        {/* Fixed header with action buttons */}
        <div className="hitl-header">
          <div className="hitl-badge">👤 Human-in-the-Loop · Review Required</div>
          <div className="hitl-title">Approve the Generated Script</div>
          <div className="hitl-sub">Review the screenplay below, then approve or reject.</div>
          <div className="hitl-actions">
            <button className="hitl-btn-reject" onClick={onReject} disabled={isApproving}>
              ✕ Reject — Start Over
            </button>
            <button className="hitl-btn-approve" onClick={onApprove} disabled={isApproving}>
              {isApproving
                ? <><div className="hitl-spinner" /> Processing...</>
                : <>✓ Approve &amp; Continue</>}
            </button>
          </div>
        </div>

        {/* Scrollable script body */}
        <div className="hitl-body">
          {script.scenes.map((scene) => (
            <div key={scene.scene_id} className="hitl-scene">
              <div className="hitl-scene-head">
                <span className="hitl-scene-id">SCENE {scene.scene_id}</span>
                <span className="hitl-scene-loc">{scene.location}</span>
              </div>

              {scene.dialogue.map((entry, idx) => (
                <div key={idx} className="hitl-line">
                  <div className="hitl-speaker">{entry.speaker}</div>
                  <div className="hitl-line-content">
                    <div className="hitl-dialogue">"{entry.line}"</div>
                    {entry.visual_cue && (
                      <div className="hitl-cue">
                        <span className="hitl-cue-icon">🎥</span>
                        <span className="hitl-cue-text">{entry.visual_cue}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>

      </div>
    </div>
  </>
);

export default HITLModal;
