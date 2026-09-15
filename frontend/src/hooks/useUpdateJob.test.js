import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import useUpdateJob, { UPDATE_JOB_STORAGE_KEY } from "./useUpdateJob";

function response(payload, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: () => Promise.resolve(payload),
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

test("stores, polls, completes, and clears an update job", async () => {
  let complete = false;
  const onComplete = vi.fn();
  vi.stubGlobal("fetch", vi.fn((url, options = {}) => {
    if (options.method === "POST") return response({ job_id: "job-1" }, 202);
    return response(!complete
      ? { job_id: "job-1", scope: "new", status: "running" }
      : { job_id: "job-1", scope: "new", status: "completed", outcome: "success", added_count: 2, failed_count: 0 });
  }));
  const { result } = renderHook(() => useUpdateJob({ onComplete, pollInterval: 1 }));

  await act(() => result.current.start({ scope: "new" }));
  expect(sessionStorage.getItem(UPDATE_JOB_STORAGE_KEY)).toBe("job-1");
  complete = true;
  await waitFor(() => expect(result.current.job?.status).toBe("completed"));
  expect(onComplete).toHaveBeenCalledWith(expect.objectContaining({ added_count: 2 }));
  expect(sessionStorage.getItem(UPDATE_JOB_STORAGE_KEY)).toBeNull();
});

test("resumes the active job reported by a 409 response", async () => {
  vi.stubGlobal("fetch", vi.fn((url, options = {}) => {
    if (options.method === "POST") {
      return response({ error: { code: "UPDATE_ALREADY_RUNNING", message: "Already running", details: { job_id: "active-job" } } }, 409);
    }
    return response({ job_id: "active-job", scope: "new", status: "completed", outcome: "no_changes", added_count: 0, failed_count: 0 });
  }));
  const { result } = renderHook(() => useUpdateJob({ pollInterval: 1 }));
  await act(() => result.current.start({ scope: "new" }));
  await waitFor(() => expect(result.current.job?.status).toBe("completed"));
  expect(fetch).toHaveBeenCalledWith("/api/update-checks/active-job", expect.any(Object));
});

test("clears an expired job restored from session storage", async () => {
  sessionStorage.setItem(UPDATE_JOB_STORAGE_KEY, "old-job");
  vi.stubGlobal("fetch", vi.fn(() => response({ error: { code: "UPDATE_JOB_NOT_FOUND", message: "Unknown" } }, 404)));
  const { result } = renderHook(() => useUpdateJob({ pollInterval: 1 }));
  await waitFor(() => expect(result.current.error).toMatch(/expired/));
  expect(result.current.job).toBeNull();
  expect(sessionStorage.getItem(UPDATE_JOB_STORAGE_KEY)).toBeNull();
});
