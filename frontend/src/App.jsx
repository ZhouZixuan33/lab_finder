import "./styles.css";


export default function App() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">I</div>
        <h1>Lab Application Tracker</h1>
      </header>

      <main className="main-content">
        <section className="welcome-card" aria-labelledby="welcome-heading">
          <p className="eyebrow">UIUC ECE</p>
          <h2 id="welcome-heading">Professor research and applications</h2>
          <p>The professor list will appear here once the API is connected.</p>
        </section>
      </main>
    </div>
  );
}
