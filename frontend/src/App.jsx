import { BrowserRouter, Route, Routes } from "react-router-dom";
import AppHeader from "./components/AppHeader";
import ProfessorListPage from "./pages/ProfessorListPage";
import "./styles.css";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <AppHeader />
        <Routes><Route path="/" element={<ProfessorListPage />} /></Routes>
      </div>
    </BrowserRouter>
  );
}
