const FIELDS = [
  ["name", "Name"],
  ["title", "Title"],
  ["email", "Email"],
  ["homepage_url", "Homepage"],
  ["lab_url", "Personal website"],
  ["prospective_students_quote", "Prospective students — evidence"],
  ["prospective_students_source_url", "Prospective students — source"],
  ["research_summary", "Research summary"],
  ["tags", "Tags"],
  ["source_urls", "Sources"],
];

function safeUrl(value) {
  if (typeof value !== "string") return null;
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

function Value({ value }) {
  if (value === null || value === undefined || value === "") return <span className="muted">—</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="muted">—</span>;
    return (
      <ul className="diff-value-list">
        {value.map((item) => <li key={String(item)}>{safeUrl(item) ? <a href={safeUrl(item)} target="_blank" rel="noreferrer">{item}</a> : item}</li>)}
      </ul>
    );
  }
  return safeUrl(value) ? <a href={safeUrl(value)} target="_blank" rel="noreferrer">{value}</a> : String(value);
}

function PublicationChanges({ title, items, kind }) {
  return (
    <section className={`publication-change publication-change--${kind}`}>
      <h3>{title} <span>{items.length}</span></h3>
      {items.length === 0
        ? <p className="muted">None</p>
        : <ul>{items.map((item) => <li key={`${item.title}-${item.year}`}><strong>{item.title}</strong><span>{[item.venue, item.year].filter(Boolean).join(" · ")}</span></li>)}</ul>}
    </section>
  );
}

export default function UpdateDiff({ proposal }) {
  const oldValues = proposal.old_values ?? {};
  const newValues = proposal.new_values ?? {};
  const publicationDiff = proposal.publication_diff ?? { added: [], removed: [] };

  return (
    <>
      <div className="diff-table-wrap">
        <table className="diff-table">
          <thead><tr><th scope="col">Field</th><th scope="col">Current</th><th scope="col">Proposed</th></tr></thead>
          <tbody>
            {FIELDS.map(([field, label]) => {
              const changed = JSON.stringify(oldValues[field]) !== JSON.stringify(newValues[field]);
              return (
                <tr key={field} className={changed ? "diff-row--changed" : ""}>
                  <th scope="row">{label}{changed && <span className="changed-label">Changed</span>}</th>
                  <td><Value value={oldValues[field]} /></td>
                  <td><Value value={newValues[field]} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="publication-diff">
        <PublicationChanges title="Publications added" items={publicationDiff.added ?? []} kind="added" />
        <PublicationChanges title="Publications removed" items={publicationDiff.removed ?? []} kind="removed" />
      </div>
      <section className="proposal-evidence">
        <h2>Evidence</h2>
        <p>Confidence: <strong>{proposal.confidence == null ? "Not provided" : `${Math.round(proposal.confidence * 100)}%`}</strong></p>
        <ul>{(proposal.source_urls ?? []).map((url) => <li key={url}><Value value={url} /></li>)}</ul>
      </section>
    </>
  );
}
