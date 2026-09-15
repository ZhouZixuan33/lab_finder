import { Link } from "react-router-dom";

const STATE_LABELS = {
  interested: "Interested",
  applied: "Applied",
  accepted: "Accepted",
  rejected: "Rejected",
};

function safeHttpUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function ExternalLink({ href, children }) {
  const safeHref = safeHttpUrl(href);
  if (!safeHref) return <span className="muted">—</span>;
  return (
    <a href={safeHref} target="_blank" rel="noreferrer">
      {children}<span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

export default function ProfessorTable({ professors }) {
  return (
    <div className="table-wrap">
      <table className="professor-table">
        <thead>
          <tr>
            <th scope="col">Name</th><th scope="col">Title</th><th scope="col">Email</th>
            <th scope="col">Personal website</th><th scope="col">Tags</th><th scope="col">Prospective students</th><th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {professors.map((professor) => (
            <tr key={professor.id}>
              <td data-label="Name"><Link className="professor-name" to={`/professors/${professor.id}`}>{professor.name}</Link></td>
              <td data-label="Title">{professor.title}</td>
              <td data-label="Email">{professor.email ? <a href={`mailto:${professor.email}`}>{professor.email}</a> : <span className="muted">—</span>}</td>
              <td data-label="Personal website"><ExternalLink href={professor.lab_url}>Personal website</ExternalLink></td>
              <td data-label="Tags">
                <div className="tag-list">
                  {professor.tags.length > 0 ? professor.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>) : <span className="muted">—</span>}
                </div>
              </td>
              <td data-label="Prospective students">
                {professor.prospective_students_quote ? <span title={professor.prospective_students_quote}>Yes</span> : null}
              </td>
              <td data-label="Status">
                {professor.application_state
                  ? <span className={`status status--${professor.application_state}`}>{STATE_LABELS[professor.application_state]}</span>
                  : <span className="muted">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
