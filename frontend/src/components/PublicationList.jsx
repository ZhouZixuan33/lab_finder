function safeUrl(value) {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

export default function PublicationList({ publications }) {
  if (publications.length === 0) return <p className="muted">No recent publications were verified.</p>;
  return (
    <ol className="publication-list">
      {publications.map((publication) => (
        <li key={publication.id}>
          <div>
            {safeUrl(publication.publication_url)
              ? <a href={safeUrl(publication.publication_url)} target="_blank" rel="noreferrer"><strong>{publication.title}</strong></a>
              : <strong>{publication.title}</strong>}
          </div>
          <p>{[publication.venue, publication.year].filter(Boolean).join(" · ")}</p>
        </li>
      ))}
    </ol>
  );
}
