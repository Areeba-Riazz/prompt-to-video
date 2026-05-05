import { useNavigate } from 'react-router-dom';

const Dashboard = () => {
  const navigate = useNavigate();

  return (
    <div className="dash-root">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=DM+Sans:wght@400;500;700&family=DM+Mono:wght@400&display=swap');
        
        .dash-root {
          min-height: 100vh;
          background: #0a0a0b;
          color: #f0e8d8;
          font-family: 'DM Sans', sans-serif;
          display: flex;
          flex-direction: column;
          align-items: center;
          padding: 80px 20px;
        }

        .dash-container {
          max-width: 1000px;
          width: 100%;
        }

        .dash-header {
          text-align: center;
          margin-bottom: 80px;
        }

        .dash-logo-eyebrow {
          font-family: 'DM Mono', monospace;
          font-size: 12px;
          letter-spacing: 0.3em;
          text-transform: uppercase;
          color: #c8a96e;
          margin-bottom: 12px;
        }

        .dash-title {
          font-family: 'Playfair Display', serif;
          font-size: 64px;
          font-weight: 700;
          letter-spacing: -0.02em;
          margin-bottom: 24px;
          line-height: 1.1;
        }

        .dash-subtitle {
          font-size: 18px;
          color: #8a8880;
          max-width: 600px;
          margin: 0 auto;
          line-height: 1.6;
        }

        .dash-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 32px;
          margin-bottom: 64px;
        }

        .dash-card {
          background: #111113;
          border: 1px solid #1e1e22;
          border-radius: 20px;
          padding: 40px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          cursor: pointer;
          display: flex;
          flex-direction: column;
          position: relative;
          overflow: hidden;
        }

        .dash-card:hover {
          border-color: #c8a96e;
          transform: translateY(-8px);
          box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        }

        .dash-card::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 4px;
          background: #c8a96e;
          opacity: 0;
          transition: opacity 0.3s;
        }

        .dash-card:hover::before {
          opacity: 1;
        }

        .dash-card-num {
          font-family: 'DM Mono', monospace;
          font-size: 14px;
          color: #c8a96e;
          margin-bottom: 24px;
          display: block;
        }

        .dash-card-title {
          font-family: 'Playfair Display', serif;
          font-size: 32px;
          margin-bottom: 16px;
        }

        .dash-card-desc {
          font-size: 15px;
          color: #8a8880;
          line-height: 1.6;
          margin-bottom: 32px;
          flex: 1;
        }

        .dash-card-footer {
          display: flex;
          align-items: center;
          gap: 12px;
          font-weight: 600;
          font-size: 14px;
          color: #c8a96e;
        }

        .dash-card-icon {
          font-size: 24px;
          margin-bottom: 20px;
        }

        .dash-stats {
          display: flex;
          justify-content: center;
          gap: 48px;
          padding: 40px;
          background: #111113;
          border: 1px solid #1e1e22;
          border-radius: 16px;
          margin-top: 40px;
        }

        .dash-stat-item {
          text-align: center;
        }

        .dash-stat-val {
          display: block;
          font-family: 'DM Mono', monospace;
          font-size: 24px;
          color: #c8a96e;
          margin-bottom: 4px;
        }

        .dash-stat-lbl {
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          color: #4a4a55;
        }

        @media (max-width: 768px) {
          .dash-grid { grid-template-columns: 1fr; }
          .dash-title { font-size: 48px; }
        }
      `}</style>

      <div className="dash-container">
        <header className="dash-header">
          <div className="dash-logo-eyebrow">End-to-End AI Cinema</div>
          <h1 className="dash-title">Project Montage</h1>
          <p className="dash-subtitle">
            A multi-agent autonomous pipeline for generating animated shorts from a single natural language prompt.
          </p>
        </header>

        <div className="dash-grid">
          <div className="dash-card" onClick={() => navigate('/phase1')}>
            <div className="dash-card-icon">✍️</div>
            <span className="dash-card-num">Phase 01</span>
            <h2 className="dash-card-title">Writer's Room</h2>
            <p className="dash-card-desc">
              Generate structured screenplays, design unique character profiles, and synthesize consistent character portraits using LLM agents.
            </p>
            <div className="dash-card-footer">
              Enter Creative Hub →
            </div>
          </div>

          <div className="dash-card" onClick={() => navigate('/phase2')}>
            <div className="dash-card-icon">🎬</div>
            <span className="dash-card-num">Phase 02</span>
            <h2 className="dash-card-title">Studio Floor</h2>
            <p className="dash-card-desc">
              Synthesize dialogue, generate cinematic footage, and apply AI face-swapping and lip-synchronization to bring your script to life.
            </p>
            <div className="dash-card-footer">
              Enter Production Studio →
            </div>
          </div>
        </div>

        <div className="dash-stats">
          <div className="dash-stat-item">
            <span className="dash-stat-val">05</span>
            <span className="dash-stat-lbl">AI Agents</span>
          </div>
          <div className="dash-stat-item">
            <span className="dash-stat-val">100%</span>
            <span className="dash-stat-lbl">Autonomous</span>
          </div>
          <div className="dash-stat-item">
            <span className="dash-stat-val">4K</span>
            <span className="dash-stat-lbl">Visuals</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
