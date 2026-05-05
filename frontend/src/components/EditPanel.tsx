import { useState, useEffect } from 'react';

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

export const EditPanel = ({ currentState, onStateUpdate, isOpen, setIsOpen }: EditPanelProps) => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [status, setStatus] = useState<string | null>(null);

  const fetchHistory = async () => {
    try {
      const res = await fetch(`${API_PHASE5}/history`);
      if (res.ok) {
        const d = await res.json();
        setHistory(d.data || []);
      }
    } catch (e) {
      console.error('Failed to fetch history', e);
    }
  };

  useEffect(() => {
    if (isOpen) fetchHistory();
  }, [isOpen]);

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

      await fetch(`${API_PHASE5}/snapshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          state: eData.data, 
          summary: `AI Edit: ${query}` 
        }),
      });

      onStateUpdate(eData.data, eData.next_step, eData.scene_id);
      setQuery('');
      setStatus('Edit applied successfully!');
      fetchHistory();
      setTimeout(() => setStatus(null), 3000);
    } catch (e: any) {
      setStatus(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRestore = async (version: string) => {
    setLoading(true);
    setStatus(`Restoring ${version}...`);
    try {
      const res = await fetch(`${API_PHASE5}/revert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || 'Revert failed');
      
      onStateUpdate(d.data);
      setStatus(`Restored to ${version}`);
      setTimeout(() => setStatus(null), 3000);
    } catch (e: any) {
      setStatus(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

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
        
        .edit-input-section { background: #0e0e10; border: 1px solid #1e1e22; border-radius: 12px; padding: 20px; }
        .edit-input-lbl { font-family: 'DM Mono', monospace; font-size: 10px; letter-spacing: 0.1em; color: #6e9ec8; margin-bottom: 12px; text-transform: uppercase; }
        .edit-textarea { width: 100%; min-height: 100px; background: #141418; border: 1px solid #2a2a30; border-radius: 8px; color: #e8e0d0; padding: 12px; font-family: 'DM Sans', sans-serif; font-size: 13px; outline: none; resize: none; transition: border-color 0.2s; margin-bottom: 12px; }
        .edit-textarea:focus { border-color: #6e9ec8; }
        
        .edit-btn { width: 100%; background: #6e9ec8; color: #fff; border: none; border-radius: 8px; padding: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s; font-size: 13px; }
        .edit-btn:hover:not(:disabled) { background: #5a8ab8; transform: translateY(-1px); }
        .edit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        
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
        .restore-btn:hover { background: #6e9ec8; color: #fff; border-color: #6e9ec8; }

        .edit-toggle-btn { position: fixed; right: 24px; bottom: 96px; width: 56px; height: 56px; border-radius: 50%; background: #111113; color: #6e9ec8; border: 1px solid #1e1e22; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 20px; z-index: 900; box-shadow: 0 4px 15px rgba(0,0,0,0.3); transition: transform 0.2s; }
        .edit-toggle-btn:hover { transform: scale(1.05); color: #fff; border-color: #6e9ec8; }
      `}</style>

      <button className="edit-toggle-btn" onClick={() => setIsOpen(true)} title="AI Edit Agent">
        ✨
      </button>

      <aside className={`edit-sidebar ${isOpen ? 'edit-sidebar--open' : ''}`}>
        <div className="edit-header">
          <div className="edit-title"><span>✨</span> Edit Agent</div>
          <button className="edit-close" onClick={() => setIsOpen(false)}>✕</button>
        </div>

        <div className="edit-body">
          <div className="edit-input-section">
            <div className="edit-input-lbl">Describe your change</div>
            <textarea 
              className="edit-textarea" 
              placeholder="e.g. 'Make the first scene darker' or 'Change Alex's voice to whispered'..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={loading}
            />
            <button className="edit-btn" onClick={handleEdit} disabled={loading || !query.trim()}>
              {loading ? 'Processing...' : 'Apply AI Edit'}
            </button>
            {status && <div className="edit-status" style={{marginTop: '12px'}}>{status}</div>}
          </div>

          <div className="history-section">
            <div className="history-title">Project Versions</div>
            <div className="history-list">
              {history.length === 0 ? (
                <div className="history-summary" style={{fontStyle:'italic'}}>No snapshots recorded yet.</div>
              ) : (
                history.slice().reverse().map((h) => (
                  <div key={h.version} className="history-item">
                    <div className="history-item-top">
                      <span className="history-v">{h.version}</span>
                      <span className="history-time">{new Date(h.timestamp).toLocaleTimeString()}</span>
                    </div>
                    <div className="history-summary">{h.summary}</div>
                    <button className="restore-btn" onClick={() => handleRestore(h.version)} disabled={loading}>
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
