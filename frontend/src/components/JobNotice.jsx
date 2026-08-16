function messageFor(job) {
  if (!job) return null;
  if (["queued", "running"].includes(job.status)) return null;
  if (job.status === "failed") return { kind: "error", text: job.error_message || "The update check failed." };
  if (job.scope === "professor") {
    return job.changed
      ? { kind: "success", text: "Changes found. Review them before updating this professor." }
      : { kind: "success", text: "No changes found for this professor." };
  }
  const messages = {
    success: { kind: "success", text: `Added ${job.added_count} new professor${job.added_count === 1 ? "" : "s"}.` },
    partial_success: { kind: "warning", text: `Added ${job.added_count} new professor${job.added_count === 1 ? "" : "s"}; ${job.failed_count} could not be added.` },
    no_changes: { kind: "success", text: "No new professors found." },
    all_failed: { kind: "error", text: `Could not add ${job.failed_count} professor${job.failed_count === 1 ? "" : "s"}.` },
  };
  return messages[job.outcome] ?? { kind: "success", text: "Update check completed." };
}

export default function JobNotice({ job, error, onDismiss }) {
  const result = error ? { kind: "error", text: error } : messageFor(job);
  if (!result) return null;
  return (
    <div className={`notice notice--${result.kind}`} role={result.kind === "error" ? "alert" : "status"}>
      <span>{result.text}</span>
      {onDismiss && <button className="notice__dismiss" type="button" aria-label="Dismiss notification" onClick={onDismiss}>×</button>}
    </div>
  );
}
