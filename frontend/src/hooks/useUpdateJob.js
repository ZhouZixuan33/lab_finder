import { useCallback, useEffect, useRef, useState } from "react";

import { getUpdateCheck, startUpdateCheck } from "../api/client";

export const UPDATE_JOB_STORAGE_KEY = "lab-tracker-active-update-job";

function storedJobId() {
  try {
    return sessionStorage.getItem(UPDATE_JOB_STORAGE_KEY);
  } catch {
    return null;
  }
}

function persistJobId(jobId) {
  try {
    if (jobId) sessionStorage.setItem(UPDATE_JOB_STORAGE_KEY, jobId);
    else sessionStorage.removeItem(UPDATE_JOB_STORAGE_KEY);
  } catch {
    // The workflow remains usable when browser storage is unavailable.
  }
}

export default function useUpdateJob({ onComplete, pollInterval = 800 } = {}) {
  const [jobId, setJobId] = useState(storedJobId);
  const [job, setJob] = useState(() => jobId ? { job_id: jobId, status: "queued" } : null);
  const [error, setError] = useState("");
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    if (!jobId) return undefined;
    let cancelled = false;
    let timer;

    async function poll() {
      try {
        const snapshot = await getUpdateCheck(jobId);
        if (cancelled) return;
        setJob(snapshot);
        setError("");
        if (["completed", "failed"].includes(snapshot.status)) {
          persistJobId(null);
          setJobId(null);
          onCompleteRef.current?.(snapshot);
          return;
        }
        timer = window.setTimeout(poll, pollInterval);
      } catch (pollError) {
        if (cancelled) return;
        persistJobId(null);
        setJobId(null);
        setJob(null);
        setError(pollError.status === 404 ? "The previous update task expired after the server restarted." : pollError.message);
      }
    }

    poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [jobId, pollInterval]);

  const start = useCallback(async (payload) => {
    setError("");
    try {
      const started = await startUpdateCheck(payload);
      persistJobId(started.job_id);
      setJob({ job_id: started.job_id, scope: payload.scope, professor_id: payload.professor_id ?? null, status: "queued" });
      setJobId(started.job_id);
      return started;
    } catch (startError) {
      if (startError.code === "UPDATE_ALREADY_RUNNING" && startError.details?.job_id) {
        const activeId = startError.details.job_id;
        persistJobId(activeId);
        setJob({ job_id: activeId, status: "queued" });
        setJobId(activeId);
        return { job_id: activeId, resumed: true };
      }
      if (startError.code === "PENDING_UPDATE_EXISTS" && startError.details?.proposal_id) {
        return { proposal_id: startError.details.proposal_id, pending: true };
      }
      setError(startError.message);
      return null;
    }
  }, []);

  const clear = useCallback(() => {
    persistJobId(null);
    setJobId(null);
    setJob(null);
    setError("");
  }, []);

  return {
    job,
    error,
    running: Boolean(jobId),
    start,
    clear,
  };
}

