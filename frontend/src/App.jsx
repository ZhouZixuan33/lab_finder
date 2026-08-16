import { BrowserRouter, Route, Routes } from "react-router-dom";
import AppHeader from "./components/AppHeader";
import ProfessorDetailPage from "./pages/ProfessorDetailPage";
import ProfessorListPage from "./pages/ProfessorListPage";
import UpdateProposalPage from "./pages/UpdateProposalPage";
import "./styles.css";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <AppHeader />
        <Routes>
          <Route path="/" element={<ProfessorListPage />} />
          <Route path="/professors/:professorId" element={<ProfessorDetailPage />} />
          <Route path="/updates/:proposalId" element={<UpdateProposalPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
