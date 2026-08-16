import { render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import App from "./App";


afterEach(() => vi.unstubAllGlobals());

test("renders the application shell", async () => {
  vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve({
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    json: () => Promise.resolve(String(url).startsWith("/api/tags")
      ? { items: [] }
      : { items: [], pagination: { page: 1, page_size: 25, total: 0, pages: 0 } }),
  })));
  render(<App />);

  expect(screen.getByRole("banner")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Professors", level: 1 }),
  ).toBeInTheDocument();
  expect(screen.getByRole("main")).toBeInTheDocument();
});
