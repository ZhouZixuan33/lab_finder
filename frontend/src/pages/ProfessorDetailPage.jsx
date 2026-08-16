import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { deleteApplication, getProfessor, saveApplication } from "../api/client";
import ApplicationForm from "../components/ApplicationForm";
import PublicationList from "../components/PublicationList";
import ResearchSummary from "../components/ResearchSummary";

function formatCheckedAt(value) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function ExternalProfileLink({ href, children }) {
  if (!href) return null;
  return <a className="button button--secondary link-button" href={href} target="_blank" rel="noreferrer">{children}</a>;
}

export default function ProfessorDetailPage() {
  const { professorId } = useParams();
  const [professor, setProfessor] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getProfessor(professorId, { signal: controller.signal })
      .then(setProfessor)
      .catch((requestError) => {
        if (requestError.name !== "AbortError") setError(requestError.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [professorId]);

  async function save(values) {
    const application = await saveApplication(professorId, values);
    setProfessor((current) => ({ ...current, application }));
    setNotice("Application saved.");
  }

  async function remove() {
    await deleteApplication(professorId);
    setProfessor((current) => ({ ...current, application: null }));
    setNotice("Application deleted.");
  }

  if (loading) return <main className="main-content"><div className="state-panel"><span className="spinner" aria-hidden="true" /> Loading professor…</div></main>;
  if (error) return <main className="main-content"><div className="state-panel state-panel--error" role="alert"><strong>Could not load professor.</strong><span>{error}</span><Link to="/">Back to professors</Link></div></main>;
  if (!professor) return null;

  return (
    <main className="main-content detail-page">
      <Link className="back-link" to="/">← Back to professors</Link>
      {notice && <div className="notice notice--success" role="status">{notice}</div>}

      <section className="detail-hero">
        <div>
          <p className="eyebrow">{professor.title}</p>
          <h1>{professor.name}</h1>
          {professor.email && <a href={`mailto:${professor.email}`}>{professor.email}</a>}
          <p className="checked-at">Last checked {formatCheckedAt(professor.last_checked_at)}</p>
        </div>
        <div className="detail-actions">
          {professor.pending_proposal_id
            ? <Link className="button button--accent link-button" to={`/updates/${professor.pending_proposal_id}`}>View pending update</Link>
            : <button className="button button--accent" type="button" data-professor-check={professor.id}>Check this professor</button>}
          <ExternalProfileLink href={professor.directory_profile_url}>UIUC profile</ExternalProfileLink>
          <ExternalProfileLink href={professor.homepage_url}>Homepage</ExternalProfileLink>
          <ExternalProfileLink href={professor.lab_url}>Lab website</ExternalProfileLink>
        </div>
      </section>

      <div className="detail-layout">
        <div className="detail-main">
          <section className="content-card" aria-labelledby="research-heading">
            <h2 id="research-heading">Research</h2>
            <ResearchSummary professor={professor} />
          </section>
          <section className="content-card" aria-labelledby="publications-heading">
            <h2 id="publications-heading">Recent publications</h2>
            <PublicationList publications={professor.publications} />
          </section>
        </div>

        <aside className="content-card application-card" aria-labelledby="application-heading">
          <p className="eyebrow">Personal tracker</p>
          <h2 id="application-heading">Application</h2>
          {!professor.application && <p className="muted">No application is tracked yet. Saving creates one.</p>}
          <ApplicationForm application={professor.application} onSave={save} onDelete={remove} />
        </aside>
      </div>
    </main>
  );
}

