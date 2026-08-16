function safeUrl(value) {
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

export default function ResearchSummary({ professor }) {
  const sourceUrls = professor.source_urls.map(safeUrl).filter(Boolean);
  return (
    <>
      <p className="research-summary">{professor.research_summary}</p>
      <div className="tag-list detail-tags">
        {professor.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
      </div>
      <details className="source-details">
        <summary>Research sources ({sourceUrls.length})</summary>
        {sourceUrls.length > 0
          ? <ul>{sourceUrls.map((url) => <li key={url}><a href={url} target="_blank" rel="noreferrer">{url}</a></li>)}</ul>
          : <p className="muted">No source links stored.</p>}
      </details>
    </>
  );
}
