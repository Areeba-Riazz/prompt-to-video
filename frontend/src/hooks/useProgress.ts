import { useState, useEffect } from 'react';

export interface ProgressUpdate {
  phase: string;
  step: string;
  status: string;
  details: string;
}

export const useProgress = () => {
  const [progress, setProgress] = useState<ProgressUpdate | null>(null);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/progress');

    ws.onopen = () => {
      console.log('✅ [WebSocket] Progress connection established.');
    };

    ws.onmessage = (event) => {
      try {
        const data: ProgressUpdate = JSON.parse(event.data);
        console.log('📥 [WebSocket] Progress Update:', data);
        setProgress(data);
      } catch (err) {
        console.error('❌ [WebSocket] Parse Error:', err);
      }
    };

    ws.onerror = (err) => {
      console.error('⚠️ [WebSocket] Error:', err);
    };

    ws.onclose = (event) => {
      console.log(`🔌 [WebSocket] Connection closed. Code: ${event.code}, Reason: ${event.reason}`);
    };

    return () => {
      console.log('🧹 [WebSocket] Cleaning up connection...');
      ws.close();
    };
  }, []);

  return progress;
};
