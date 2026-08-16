import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, vi } from "vitest";

import ProfessorListPage from "./ProfessorListPage";

const CATALOG = {
  items: [{
    id: 7,
    name: "Alice Systems",
    title: "Professor",
    email: "alice@illinois.edu",
    lab_url: "https://alice.example.edu/lab",
    tags: ["Architecture", "Reliable AI"],
    application_state: null,
  }],
  pagination: { page: 1, page_size: 25, total: 1, pages: 1 },
};

function jsonResponse(payload, ok = true) {
  return Promise.resolve({
    ok,
    status: ok ? 200 : 500,
    headers: { get: () => "application/json" },
    json: () => Promise.resolve(payload),
  });
}

function mockCatalog(catalog = CATALOG) {
  vi.stubGlobal("fetch", vi.fn((url) => {
    if (String(url).startsWith("/api/tags")) return jsonResponse({ items: [{ tag: "architecture", professor_count: 1 }] });
    return jsonResponse(catalog);
  }));
}

afterEach(() => vi.unstubAllGlobals());

test("shows the professor catalog and uses a dash for no application", async () => {
  mockCatalog();
  render(<MemoryRouter><ProfessorListPage /></MemoryRouter>);
  expect(await screen.findByRole("link", { name: "Alice Systems" })).toHaveAttribute("href", "/professors/7");
  expect(screen.getByRole("link", { name: /Visit lab/ })).toHaveAttribute("rel", "noreferrer");
  expect(screen.getByRole("cell", { name: "—" })).toBeInTheDocument();
});

test("writes search, status, and tag filters into the request URL", async () => {
  mockCatalog();
  const user = userEvent.setup();
  render(<MemoryRouter><ProfessorListPage /></MemoryRouter>);
  await screen.findByText("Alice Systems");
  await user.type(screen.getByRole("searchbox", { name: "Search professors" }), "systems");
  await user.click(screen.getByRole("button", { name: "Search" }));
  await user.selectOptions(screen.getByLabelText("Application status"), "interested");
  await user.click(await screen.findByRole("checkbox", { name: /architecture/ }));

  await waitFor(() => {
    const calls = fetch.mock.calls.map(([url]) => String(url)).filter((url) => url.startsWith("/api/professors"));
    expect(calls.some((url) => url.includes("q=systems"))).toBe(true);
    expect(calls.some((url) => url.includes("state=interested"))).toBe(true);
    expect(calls.some((url) => url.includes("tags=architecture"))).toBe(true);
  });
});

test("shows empty and API error states", async () => {
  mockCatalog({ items: [], pagination: { page: 1, page_size: 25, total: 0, pages: 0 } });
  const { unmount } = render(<MemoryRouter><ProfessorListPage /></MemoryRouter>);
  expect(await screen.findByText("No professors found.")).toBeInTheDocument();
  unmount();

  vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ error: { message: "Database unavailable" } }, false)));
  render(<MemoryRouter><ProfessorListPage /></MemoryRouter>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Database unavailable");
});

