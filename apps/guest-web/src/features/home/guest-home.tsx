export function GuestHome() {
  return (
    <section className="welcome" aria-labelledby="welcome-title">
      <div className="welcome-copy">
        <h1 id="welcome-title">Guest services</h1>
        <p>
          A thoughtful, simple way to get help during your stay.
        </p>
      </div>
      <aside className="preview-note" aria-label="Preview status">
        <span className="preview-indicator" aria-hidden="true" />
        <p>
          This preview is not connected to hotel systems. No guest information
          is loaded or saved here.
        </p>
      </aside>
    </section>
  );
}
