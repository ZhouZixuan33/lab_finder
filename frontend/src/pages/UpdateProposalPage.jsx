import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { applyUpdateProposal, getUpdateProposal, rejectUpdateProposal } from "../api/client";
import UpdateDiff from "../components/UpdateDiff";

export default function UpdateProposalPage() {
  const { proposalId } = useParams();
  const [proposal, setProposal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getUpdateProposal(proposalId, { signal: controller.signal })
      .then(setProposal)
      .catch((requestError) => {
        if (requestError.name !== "AbortError") setError(requestError.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [proposalId]);

  async function resolve(action) {
    setBusy(true);
    setError("");
    try {
      const resolved = action === "apply"
        ? await applyUpdateProposal(proposalId)
        : await rejectUpdateProposal(proposalId);
      setProposal(resolved);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <main className="main-content"><div className="state-panel"><span className="spinner" aria-hidden="true" /> Loading update…</div></main>;
  if (!proposal) return <main className="main-content"><div className="state-panel state-panel--error" role="alert"><strong>Could not load update.</strong><span>{error}</span><Link to="/">Back to professors</Link></div></main>;

  const pending = proposal.status === "pending";
  return (
    <main className="main-content proposal-page">
      <Link className="back-link" to={`/professors/${proposal.professor_id}`}>← Back to professor</Link>
      <section className="page-heading proposal-heading">
        <div>
          <p className="eyebrow">Review required</p>
          <h1>Professor update</h1>
          <p>Compare the current record with the newly researched result. The update is applied as one transaction.</p>
        </div>
        <span className={`proposal-status proposal-status--${proposal.status}`}>{proposal.status}</span>
      </section>

      {error && <div className="notice notice--error" role="alert">{error}</div>}
      {!pending && <div className="notice notice--success" role="status">This proposal was {proposal.status}. It cannot be changed again.</div>}
      <UpdateDiff proposal={proposal} />

      {pending && (
        <div className="proposal-actions">
          <button className="button button--primary" type="button" disabled={busy} onClick={() => resolve("apply")}>{busy ? "Saving…" : "Apply all changes"}</button>
          <button className="button button--danger" type="button" disabled={busy} onClick={() => resolve("reject")}>Reject update</button>
          <p>Application status, date, and notes are never changed by this action.</p>
        </div>
      )}
    </main>
  );
}

