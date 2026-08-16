import { expect, test } from "@playwright/test";

const professor = {
  id: 7,
  name: "Alice Systems",
  title: "Professor",
  email: "alice@illinois.edu",
  directory_profile_url: "https://ece.illinois.edu/alice",
  homepage_url: "https://alice.example.edu",
  lab_url: "https://alice.example.edu/lab",
  research_summary: "Alice studies dependable computer systems and AI accelerators.",
  tags: ["Architecture", "Reliable AI"],
  source_urls: ["https://ece.illinois.edu/alice"],
  source_hash: "hash",
  created_at: "2026-08-16T10:00:00Z",
  last_checked_at: "2026-08-16T10:00:00Z",
  updated_at: "2026-08-16T10:00:00Z",
  publications: [{ id: 3, professor_id: 7, title: "Reliable Accelerators", year: 2026, venue: "ExampleConf", publication_url: null, doi: null, source: "openalex", created_at: "2026-08-16T10:00:00Z" }],
  application: null,
  pending_proposal_id: null,
};

test("searches the catalog, opens details, and saves an application", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.route((url) => url.pathname.startsWith("/api/"), async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/tags") return route.fulfill({ json: { items: [{ tag: "architecture", professor_count: 1 }] } });
    if (url.pathname === "/api/professors" && request.method() === "GET") {
      return route.fulfill({ json: { items: [{ ...professor, application_state: null }], pagination: { page: 1, page_size: 25, total: 1, pages: 1 } } });
    }
    if (url.pathname === "/api/professors/7" && request.method() === "GET") return route.fulfill({ json: professor });
    if (url.pathname === "/api/professors/7/application" && request.method() === "PUT") {
      return route.fulfill({ json: { id: 9, professor_id: 7, ...(await request.postDataJSON()), updated_at: "2026-08-16T12:00:00Z" } });
    }
    return route.fulfill({ status: 404, json: { error: { message: "Not mocked" } } });
  });

  await page.goto("/");
  await page.waitForTimeout(100);
  expect(pageErrors).toEqual([]);
  await expect(page.getByRole("heading", { name: "Professors" })).toBeVisible();
  await page.getByRole("searchbox", { name: "Search professors" }).fill("systems");
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("link", { name: "Alice Systems" }).click();
  await expect(page.getByText("Alice studies dependable computer systems and AI accelerators.")).toBeVisible();

  await page.getByLabel("Status").selectOption("applied");
  await page.getByLabel("Application date").fill("2026-08-16");
  await page.getByLabel("Notes").fill("Submitted to the lab portal.");
  await page.getByRole("button", { name: "Save application" }).click();
  await expect(page.getByRole("status")).toContainText("Application saved");
});
