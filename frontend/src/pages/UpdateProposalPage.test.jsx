import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, vi } from "vitest";

import UpdateProposalPage from "./UpdateProposalPage";

const PROPOSAL = {
  id: 19,
  job_id: "job-19",
  professor_id: 7,
  status: "pending",
  old_values: {
    name: "Alice Systems",
    title: "Professor",
    email: "alice@illinois.edu",
    homepage_url: "https://alice.example.edu",
    lab_url: "https://alice.example.edu/old-lab",
    research_summary: "Old research summary.",
    tags: ["Architecture"],
    source_urls: ["https://ece.illinois.edu/alice"],
  },
  new_values: {
    name: "Alice Systems",
    title: "Professor",
    email: "alice@illinois.edu",
    homepage_url: "https://alice.example.edu",
    lab_url: "https://alice.example.edu/new-lab",
    research_summary: "New research summary.",
    tags: ["Reliable AI"],
    source_urls: ["https://ece.illinois.edu/alice", "https://alice.example.edu/new-lab"],
  },
  publication_diff: {
    added: [{ title: "Dependable AI Hardware", year: 2026, venue: "ExampleConf" }],
    removed: [{ title: "Old Paper", year: 2024, venue: null }],
    proposed: [],
  },
  source_urls: ["https://alice.example.edu/new-lab"],
  confidence: 0.92,
};

function response(payload) {
  return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve(payload) });
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/updates/19"]}>
      <Routes><Route path="/updates/:proposalId" element={<UpdateProposalPage />} /></Routes>
    </MemoryRouter>,
  );
}

afterEach(() => vi.unstubAllGlobals());

test("shows field and publication differences and applies the proposal as a whole", async () => {
  vi.stubGlobal("fetch", vi.fn((url, options = {}) => options.method === "POST" ? response({ ...PROPOSAL, status: "applied" }) : response(PROPOSAL)));
  const user = userEvent.setup();
  renderPage();

  expect(await screen.findByRole("heading", { name: "Professor update" })).toBeInTheDocument();
  expect(screen.getByText("Old research summary.")).toBeInTheDocument();
  expect(screen.getByText("New research summary.")).toBeInTheDocument();
  expect(screen.getByText("Dependable AI Hardware")).toBeInTheDocument();
  expect(screen.getByText("Confidence:").parentElement).toHaveTextContent("92%");
  await user.click(screen.getByRole("button", { name: "Apply all changes" }));

  expect(await screen.findByText("This proposal was applied. It cannot be changed again.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Apply all changes" })).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith("/api/update-proposals/19/apply", expect.objectContaining({ method: "POST" }));
});
