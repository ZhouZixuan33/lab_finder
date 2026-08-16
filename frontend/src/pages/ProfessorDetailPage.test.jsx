import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, vi } from "vitest";

import ProfessorDetailPage from "./ProfessorDetailPage";

const PROFESSOR = {
  id: 7,
  name: "Alice Systems",
  title: "Professor",
  email: "alice@illinois.edu",
  directory_profile_url: "https://ece.illinois.edu/alice",
  homepage_url: "https://alice.example.edu",
  lab_url: "https://alice.example.edu/lab",
  research_summary: "Alice studies dependable computer systems.",
  tags: ["Architecture"],
  source_urls: ["https://ece.illinois.edu/alice"],
  publications: [{ id: 2, title: "Reliable Accelerators", year: 2026, venue: "ExampleConf", publication_url: null }],
  application: null,
  pending_proposal_id: null,
  last_checked_at: "2026-08-16T10:00:00Z",
};

function response(payload, { status = 200 } = {}) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => status === 204 ? "" : "application/json" },
    json: () => Promise.resolve(payload),
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/professors/7"]}>
      <Routes><Route path="/professors/:professorId" element={<ProfessorDetailPage />} /></Routes>
    </MemoryRouter>,
  );
}

afterEach(() => vi.unstubAllGlobals());

test("shows research, publications, and saves an application explicitly", async () => {
  vi.stubGlobal("fetch", vi.fn((url, options = {}) => {
    if (options.method === "PUT") {
      return response({ id: 4, professor_id: 7, state: "applied", application_date: "2026-08-16", notes: "Submitted", updated_at: "2026-08-16T11:00:00Z" });
    }
    return response(PROFESSOR);
  }));
  const user = userEvent.setup();
  renderPage();

  expect(await screen.findByRole("heading", { name: "Alice Systems" })).toBeInTheDocument();
  expect(screen.getByText("Alice studies dependable computer systems.")).toBeInTheDocument();
  expect(screen.getByText("Reliable Accelerators")).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Status"), "applied");
  await user.type(screen.getByLabelText("Application date"), "2026-08-16");
  await user.type(screen.getByLabelText("Notes"), "Submitted");
  await user.click(screen.getByRole("button", { name: "Save application" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Application saved.");
  const putCall = fetch.mock.calls.find(([, options]) => options?.method === "PUT");
  expect(JSON.parse(putCall[1].body)).toEqual({ state: "applied", application_date: "2026-08-16", notes: "Submitted" });
});

test("deletes an existing application and returns to the empty state", async () => {
  const existing = { id: 4, professor_id: 7, state: "interested", application_date: null, notes: "Draft", updated_at: "2026-08-16T11:00:00Z" };
  vi.stubGlobal("fetch", vi.fn((url, options = {}) => options.method === "DELETE" ? response(null, { status: 204 }) : response({ ...PROFESSOR, application: existing })));
  const user = userEvent.setup();
  renderPage();
  await user.click(await screen.findByRole("button", { name: "Delete application" }));
  expect(await screen.findByText("No application is tracked yet. Saving creates one.")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith("/api/professors/7/application", expect.objectContaining({ method: "DELETE" }));
});

test("replaces the check button when a pending proposal exists", async () => {
  vi.stubGlobal("fetch", vi.fn(() => response({ ...PROFESSOR, pending_proposal_id: 19 })));
  renderPage();
  expect(await screen.findByRole("link", { name: "View pending update" })).toHaveAttribute("href", "/updates/19");
  expect(screen.queryByRole("button", { name: "Check this professor" })).not.toBeInTheDocument();
});
