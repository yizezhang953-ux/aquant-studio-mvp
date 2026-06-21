const modules = [
  ["Templates", "Create strategies from A-share templates"],
  ["Strategy Editor", "Edit DSL rules, position sizing, and risk controls"],
  ["Backtests", "Run historical backtests and inspect reports"],
  ["Optimization", "Compare parameter combinations"],
  ["Paper Trading", "Replay strategies in sandbox mode"],
  ["Security", "Keep live trading blocked until production controls exist"],
];

export default function App() {
  return (
    <main className="shell">
      <header className="hero">
        <span className="badge">Web App Stage 1</span>
        <h1>AQuant Studio</h1>
        <p>
          Online application structure for the A-share quantitative strategy
          platform. The backend API and frontend shell are ready for staged
          migration from the current MVP modules.
        </p>
      </header>

      <section className="status">
        <div>
          <span>Market</span>
          <strong>A-share</strong>
        </div>
        <div>
          <span>Backend</span>
          <strong>FastAPI</strong>
        </div>
        <div>
          <span>Frontend</span>
          <strong>React</strong>
        </div>
        <div className="blocked">
          <span>Live Trading</span>
          <strong>Blocked</strong>
        </div>
      </section>

      <section className="modules">
        {modules.map(([title, description]) => (
          <article key={title}>
            <h2>{title}</h2>
            <p>{description}</p>
          </article>
        ))}
      </section>
    </main>
  );
}
