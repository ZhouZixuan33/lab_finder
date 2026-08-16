import { useEffect, useState } from "react";

const APPLICATION_STATES = [
  ["interested", "Interested"],
  ["applied", "Applied"],
  ["accepted", "Accepted"],
  ["rejected", "Rejected"],
];

function formValues(application) {
  return {
    state: application?.state ?? "interested",
    application_date: application?.application_date ?? "",
    notes: application?.notes ?? "",
  };
}

export default function ApplicationForm({ application, onSave, onDelete }) {
  const [values, setValues] = useState(() => formValues(application));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => setValues(formValues(application)), [application]);

  function setField(field, value) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await onSave({
        state: values.state,
        application_date: values.application_date || null,
        notes: values.notes.trim(),
      });
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    setSaving(true);
    setError("");
    try {
      await onDelete();
    } catch (deleteError) {
      setError(deleteError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="application-form" onSubmit={submit}>
      <div className="form-grid">
        <label className="field">
          <span>Status</span>
          <select value={values.state} onChange={(event) => setField("state", event.target.value)}>
            {APPLICATION_STATES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Application date</span>
          <input type="date" value={values.application_date} onChange={(event) => setField("application_date", event.target.value)} />
        </label>
      </div>
      <label className="field">
        <span>Notes</span>
        <textarea rows="6" value={values.notes} placeholder="Follow-up notes, contacts, or next steps" onChange={(event) => setField("notes", event.target.value)} />
      </label>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="form-actions">
        <button className="button button--primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save application"}</button>
        {application && <button className="button button--danger" type="button" disabled={saving} onClick={remove}>Delete application</button>}
      </div>
    </form>
  );
}

