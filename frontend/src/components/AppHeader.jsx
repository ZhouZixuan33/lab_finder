import { Link } from "react-router-dom";
import blockI from "../assets/block-i.png";

export default function AppHeader() {
  return (
    <header className="topbar">
      <div className="topbar__inner">
        <Link className="brand-link" to="/" aria-label="Lab Application Tracker home">
          <img className="brand-logo" src={blockI} alt="Block I in Illini orange" />
          <span>Lab Application Tracker</span>
        </Link>
      </div>
    </header>
  );
}

