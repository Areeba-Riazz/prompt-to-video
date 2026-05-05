# Project Montage — Frontend

This is the user interface for the **Project Montage** agentic AI video pipeline. It allows users to input story prompts, review scripts via HITL (Human-in-the-Loop), and preview generated movie scenes.

## 🚀 Getting Started

### Prerequisites
*   [Node.js](https://nodejs.org/) (v18 or higher recommended)
*   [npm](https://www.npmjs.com/)

### Installation
```bash
# From the project root
cd frontend
npm install
```

### Development
```bash
npm run dev
```
The application will be available at [http://localhost:5173](http://localhost:5173).

## 🛠️ Tech Stack
*   **Framework:** [React 19](https://react.dev/)
*   **Build Tool:** [Vite](https://vitejs.dev/)
*   **Styling:** [Tailwind CSS 4](https://tailwindcss.com/)
*   **Routing:** [React Router 7](https://reactrouter.com/)
*   **Language:** [TypeScript](https://www.typescriptlang.org/)

## 📂 Structure
*   `src/pages/Phase1.tsx`: The "Writer's Room" interface for script generation and character design.
*   `src/pages/Phase2.tsx`: The "Studio Floor" interface for audio/video synthesis and scene playback. Includes the **Edit Agent Sidebar**.
*   `src/components/EditPanel.tsx`: The collapsible AI Edit Agent interface for natural language feedback and snapshot management.
*   `src/pages/HITLModal.tsx`: The review interface for script approval.

## 🌐 API Integration
The frontend communicates with the FastAPI backend at `http://127.0.0.1:8000`. Ensure the backend is running for the pipeline to function.

## 🎨 Phase 5: Intelligent Edit Agent
The frontend now features a right-aligned, collapsible **Edit Agent** sidebar that provides:
- **Natural Language Control**: Chat with the agent to request surgical changes (e.g., *"Make Alex sound more like a robot"*).
- **Snapshot Browser**: View and revert to previous versions of your project.
- **Production Progress**: A dynamic progress bar that highlights **Post-Processing** steps for near-instant stylistic edits.
