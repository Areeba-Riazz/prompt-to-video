import { useState, useEffect, useCallback, useMemo } from 'react';

const API_PHASE5 = 'http://localhost:8000/api/phase5';

interface Snapshot {
  version: string;
  timestamp: string;
  summary: string;
  assets_count: number;
}

interface EditPanelProps {
  currentState: any;
  onStateUpdate: (newState: any, nextStep?: string, sceneId?: number) => void;
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
}

/** History from API is append order: index 0 = oldest, length-1 = newest. */
export const EditPanel = ({ currentState, onStateUpdate, isOpen, setIsOpen }: EditPanelProps) => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<Snapshot[]>([]);
  /** Index into `history` (chronological). -1 = no snapshots. */
  const [currentVersionIndex, setCurrentVersionIndex] = useState(-1);
  const [status, setStatus] = useState<string | null>(null);
  const [pendingRestoreVersion, setPendingRestoreVersion] = useState<string | null>(null);

  const fetchHistory = useCallback(async (opts?: { selectLatest?: boolean }) => {
    try {
      const res = await fetch(`${API_PHASE5}/history`);
      if (!res.ok) return;
      const d = await res.json();
      const list: Snapshot[] = d.data || [];
      setHistory(list);
      setCurrentVersionIndex((idx) => {
        if (opts?.selectLatest && list.length) return list.length - 1;
        if (list.length && idx === -1) return list.length - 1;
        if (list.length && idx >= list.length) return list.length - 1;
        return idx;
      });
    } catch (e) {
      console.error('Failed to fetch history', e);
    }
  }, []);

  useEffect(() => {
    if (isOpen) void fetchHistory();
  }, [isOpen, fetchHistory]);

  const applyVersionLabel = useMemo(() => {
    if (!history.length) return 'No snapshots yet';
    if (currentVersionIndex < 0 || currentVersionIndex >= history.length) return '—';
    const atTip = currentVersionIndex === history.length - 1;
    if (atTip) return 'Latest';
    return history[currentVersionIndex]?.version ?? '—';
  }, [history, currentVersionIndex]);

  const applyRevert = async (version: string, nextIndex: number) => {
    const res = await fetch(`${API_PHASE5}/revert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version }),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.detail || 'Revert failed');
    onStateUpdate(d.data);
    setCurrentVersionIndex(nextIndex);
    await fetchHistory();
  };

  const handleUndo = async () => {
    if (currentVersionIndex <= 0 || loading) return;
    const newIdx = currentVersionIndex - 1;
    const entry = history[newIdx];
    if (!entry) return;
    setLoading(true);
    setStatus(`Undo → ${entry.version}…`);
    try {
      await applyRevert(entry.version, newIdx);
      setStatus(`Restored to ${entry.version}`);
      setTimeout(() => setStatus(null), 2500);
    } catch (e: unknown) {
      setStatus(`Error: ${e instanceof Error ? e.message : 'Undo failed'}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDo = async () => {
    if (currentVersionIndex < 0 || currentVersionIndex >= history.length - 1 || loading) return;
    const newIdx = currentVersionIndex + 1;
    const entry = history[newIdx];
    if (!entry) return;
    setLoading(true);
    setStatus(`Do → ${entry.version}…`);
    try {
      await applyRevert(entry.version, newIdx);
      setStatus(`Restored to ${entry.version}`);
      setTimeout(() => setStatus(null), 2500);
    } catch (e: unknown) {
      setStatus(`Error: ${e instanceof Error ? e.message : 'Do failed'}`);
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setStatus('Analyzing intent...');
    try {
      const iRes = await fetch(`${API_PHASE5}/intent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, current_state: currentState }),
      });
      const iData = await iRes.json();
      const intent = iData.data;

      if (!intent || intent.target === 'unknown') {
        throw new Error('Could not understand instruction.');
      }

      setStatus(`Executing ${intent.intent}...`);

      const eRes = await fetch(`${API_PHASE5}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ intent_obj: intent, state: currentState }),
      });
      const eData = await eRes.json();

      if (!eRes.ok) throw new Error(eData.detail || 'Edit execution failed');
      if (eData.error) throw new Error(String(eData.error));

      const atTip = currentVersionIndex < 0 || currentVersionIndex >= history.length - 1;
      const branchVersion =
        !atTip && history.length > 0 && currentVersionIndex >= 0
          ? history[currentVersionIndex]?.version
          : undefined;

      await fetch(`${API_PHASE5}/snapshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          state: eData.data,
          summary: `AI Edit: ${query}`,
          ...(branchVersion ? { truncate_after_version: branchVersion } : {}),
        }),
      });

      onStateUpdate(eData.data, eData.next_step, eData.scene_id);
      setQuery('');
      setStatus('Edit applied successfully!');
      await fetchHistory({ selectLatest: true });
      setTimeout(() => setStatus(null), 3000);
    } catch (e: unknown) {
      setStatus(`Error: ${e instanceof Error ? e.message : 'Request failed'}`);
    } finally {
      setLoading(false);
    }
  };

  const runRestore = async (version: string) => {
    const idx = history.findIndex((h) => h.version === version);
    setLoading(true);
    setStatus(`Restoring ${version}...`);
    try {
      await applyRevert(version, idx >= 0 ? idx : currentVersionIndex);
      setStatus(`Restored to ${version}`);
      setTimeout(() => setStatus(null), 3000);
    } catch (e: unknown) {
      setStatus(`Error: ${e instanceof Error ? e.message : 'Revert failed'}`);
    } finally {
      setLoading(false);
      setPendingRestoreVersion(null);
    }
  };

  const canUndo = history.length > 0 && currentVersionIndex > 0;
  const canDo = history.length > 0 && currentVersionIndex >= 0 && currentVersionIndex < history.length - 1;

  return (
    <>
      <style>{`
        .edit-sidebar { 
          position: fixed; top: 0; right: 0; bottom: 0; width: 360px; 
          background: #111113; border-left: 1px solid #1e1e22; 
          transform: translateX(100%); transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1); 
          z-index: 1001; display: flex; flex-direction: column; 
          box-shadow: -10px 0 30px rgba(0,0,0,0.5);
        }
        .edit-sidebar--open { transform: translateX(0); }
        
        .edit-header { padding: 24px; border-bottom: 1px solid #1e1e22; display: flex; align-items: center; justify-content: space-between; }
        .edit-title { font-family: 'Playfair Display', serif; font-size: 18px; font-weight: 600; color: #f0e8d8; display: flex; align-items: center; gap: 10px; }
        .edit-close { background: none; border: none; color: #4a4a55; cursor: pointer; font-size: 18px; }

        .edit-body { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 20px; }

        .edit-nav-row {
          display: flex; justify-content: flex-end; align-items: center; gap: 4px;
          margin-bottom: 8px; user-select: none;
        }
        .edit-nav-btn {
          font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
          font-size: 11px; line-height: 1.2; padding: 2px 8px; min-height: 22px;
          background: #1a1a1e; border: 1px solid #2e2e34; color: #c4bcb0; border-radius: 3px;
          cursor: pointer; transition: background 0.12s, border-color 0.12s;
        }
        .edit-nav-btn:hover:not(:disabled) {
          background: #222228; border-color: #3a3a44; color: #eae4dc;
        }
        .edit-nav-btn:disabled {
          opacity: 0.38; cursor: default; color: #5a5a62;
        }
        
        .edit-input-section { background: #0e0e10; border: 1px solid #1e1e22; border-radius: 12px; padding: 20px; }
        .edit-input-lbl { font-family: 'DM Mono', monospace; font-size: 10px; letter-spacing: 0.1em; color: #6e9ec8; margin-bottom: 12px; text-transform: uppercase; }
        .edit-textarea { width: 100%; min-height: 100px; background: #141418; border: 1px solid #2a2a30; border-radius: 8px; color: #e8e0d0; padding: 12px; font-family: 'DM Sans', sans-serif; font-size: 13px; outline: none; resize: none; transition: border-color 0.2s; margin-bottom: 12px; }
        .edit-textarea:focus { border-color: #6e9ec8; }
        
        .edit-btn { width: 100%; background: #6e9ec8; color: #fff; border: none; border-radius: 8px; padding: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s; font-size: 13px; }
        .edit-btn:hover:not(:disabled) { background: #5a8ab8; transform: translateY(-1px); }
        .edit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

        .edit-apply-version {
          font-family: 'DM Mono', monospace; font-size: 10px; color: #5a5a65; margin-top: 8px; text-align: center; letter-spacing: 0.04em;
        }
        .edit-apply-version strong { color: #8a8a96; font-weight: 600; }
        
        .edit-status { font-family: 'DM Mono', monospace; font-size: 11px; color: #6e9ec8; line-height: 1.4; }
        
        .history-section { border-top: 1px solid #1e1e22; padding-top: 20px; }
        .history-title { font-family: 'DM Mono', monospace; font-size: 10px; color: #4a4a55; margin-bottom: 12px; text-transform: uppercase; }
        .history-list { display: flex; flex-direction: column; gap: 10px; }
        .history-item { background: #0e0e10; padding: 12px; border-radius: 8px; border: 1px solid #1e1e22; display: flex; flex-direction: column; gap: 8px; }
        .history-item-top { display: flex; justify-content: space-between; align-items: center; }
        .history-v { font-family: 'DM Mono', monospace; font-size: 11px; color: #6e9ec8; font-weight: 600; }
        .history-time { font-size: 10px; color: #3a3a44; }
        .history-summary { font-size: 12px; color: #b0a898; line-height: 1.4; }
        .restore-btn { background: #1e1e22; border: 1px solid #2a2a30; color: #9a9288; font-size: 11px; padding: 6px 12px; border-radius: 6px; cursor: pointer; transition: all 0.2s; align-self: flex-end; }
        .restore-btn:hover:not(:disabled) { background: #6e9ec8; color: #fff; border-color: #6e9ec8; }
        .restore-btn:disabled { opacity: 0.45; cursor: not-allowed; }

        .edit-toggle-btn { position: fixed; right: 24px; bottom: 96px; width: 56px; height: 56px; border-radius: 50%; background: #111113; color: #6e9ec8; border: 1px solid #1e1e22; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 20px; z-index: 900; box-shadow: 0 4px 15px rgba(0,0,0,0.3); transition: transform 0.2s; }
        .edit-toggle-btn:hover { transform: scale(1.05); color: #fff; border-color: #6e9ec8; }

        .edit-modal-overlay {
          position: fixed; inset: 0; background: rgba(0,0,0,0.55); z-index: 2000;
          display: flex; align-items: center; justify-content: center; padding: 24px;
        }
        .edit-modal {
          background: #111113; border: 1px solid #2a2a30; border-radius: 12px; padding: 24px; max-width: 380px; width: 100%;
          box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        }
        .edit-modal-title { font-family: 'Playfair Display', serif; font-size: 18px; color: #f0e8d8; margin-bottom: 12px; }
        .edit-modal-body { font-size: 14px; color: #9a9288; line-height: 1.5; margin-bottom: 20px; }
        .edit-modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
        .edit-modal-cancel {
          background: transparent; border: 1px solid #2a2a30; color: #9a9288; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-size: 13px;
        }
        .edit-modal-cancel:hover { border-color: #4a4a55; color: #c8c0b0; }
        .edit-modal-confirm {
          background: #6e9ec8; border: none; color: #fff; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600;
        }
        .edit-modal-confirm:hover:not(:disabled) { background: #5a8ab8; }
        .edit-modal-confirm:disabled { opacity: 0.5; cursor: not-allowed; }
      `}</style>

      <button type="button" className="edit-toggle-btn" onClick={() => setIsOpen(true)} title="AI Edit Agent">
        ✨
      </button>

      {pendingRestoreVersion && (
        <div
          className="edit-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="restore-confirm-title"
          onClick={(e) => e.target === e.currentTarget && !loading && setPendingRestoreVersion(null)}
        >
          <div className="edit-modal" onClick={(e) => e.stopPropagation()}>
            <div id="restore-confirm-title" className="edit-modal-title">
              Restore this version?
            </div>
            <div className="edit-modal-body">
              Are you sure you want to restore <strong style={{ color: '#e8e0d0' }}>{pendingRestoreVersion}</strong>?
              This will replace the current project state and any files saved in that snapshot.
            </div>
            <div className="edit-modal-actions">
              <button
                type="button"
                className="edit-modal-cancel"
                disabled={loading}
                onClick={() => setPendingRestoreVersion(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="edit-modal-confirm"
                disabled={loading}
                onClick={() => void runRestore(pendingRestoreVersion)}
              >
                {loading ? 'Restoring…' : 'Yes, restore'}
              </button>
            </div>
          </div>
        </div>
      )}

      <aside className={`edit-sidebar ${isOpen ? 'edit-sidebar--open' : ''}`}>
        <div className="edit-header">
          <div className="edit-title"><span>✨</span> Edit Agent</div>
          <button type="button" className="edit-close" onClick={() => setIsOpen(false)}>✕</button>
        </div>

        <div className="edit-body">
          <div className="edit-input-section">
            <div className="edit-input-lbl">Version history</div>
            <div className="edit-nav-row" aria-label="Version navigation">
              <button
                type="button"
                className="edit-nav-btn"
                onClick={() => void handleUndo()}
                disabled={!canUndo || loading}
                title="Previous version"
              >
                Undo
              </button>
              {canDo ? (
                <button
                  type="button"
                  className="edit-nav-btn"
                  onClick={() => void handleDo()}
                  disabled={loading}
                  title="Next version"
                >
                  Do
                </button>
              ) : null}
            </div>
            <p className="edit-status" style={{ marginTop: '6px', marginBottom: '0', color: '#5a5a65', fontSize: '10px' }}>
              New edits drop any forward versions and keep Undo only.
            </p>
          </div>

          <div className="edit-input-section">
            <div className="edit-input-lbl">Describe your change</div>
            <textarea
              className="edit-textarea"
              placeholder="e.g. 'Make the first scene darker' or 'Change Alex's voice to whispered'..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={loading}
            />
            <button type="button" className="edit-btn" onClick={() => void handleEdit()} disabled={loading || !query.trim()}>
              {loading ? 'Processing...' : 'Apply AI Edit'}
            </button>
            <div className="edit-apply-version">
              Applying to: <strong>{applyVersionLabel}</strong>
            </div>
            {status && <div className="edit-status" style={{ marginTop: '12px' }}>{status}</div>}
          </div>

          <div className="history-section">
            <div className="history-title">Project Versions</div>
            <div className="history-list">
              {history.length === 0 ? (
                <div className="history-summary" style={{ fontStyle: 'italic' }}>No snapshots recorded yet.</div>
              ) : (
                history
                  .slice()
                  .reverse()
                  .map((h) => (
                    <div key={h.version} className="history-item">
                      <div className="history-item-top">
                        <span className="history-v">{h.version}</span>
                        <span className="history-time">{new Date(h.timestamp).toLocaleString()}</span>
                      </div>
                      <div className="history-summary">{h.summary}</div>
                      <button
                        type="button"
                        className="restore-btn"
                        onClick={() => setPendingRestoreVersion(h.version)}
                        disabled={loading}
                      >
                        Restore Version
                      </button>
                    </div>
                  ))
              )}
            </div>
          </div>
        </div>
      </aside>
    </>
  );
};
