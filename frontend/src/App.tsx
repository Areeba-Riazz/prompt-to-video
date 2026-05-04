import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Phase1 from './pages/Phase1';
import Phase2 from './pages/Phase2';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Phase1 />} />
        <Route path="/phase2" element={<Phase2 />} />
      </Routes>
    </Router>
  );
}

export default App;
