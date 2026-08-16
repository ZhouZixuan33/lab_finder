import { expect, test } from "@playwright/test";

test("shows only compact feedback for a partially successful discovery", async ({ page }) => {
  let catalogRequests = 0;
  let jobPolls = 0;
  await page.route((url) => url.pathname.startsWith("/api/"), async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/tags") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/professors") {
      catalogRequests += 1;
      const items = catalogRequests > 1 ? [{ id: 21, name: "New Professor", title: "Assistant Professor", email: "new@illinois.edu", lab_url: null, tags: ["Photonics"], application_state: null }] : [];
      return route.fulfill({ json: { items, pagination: { page: 1, page_size: 25, total: items.length, pages: items.length ? 1 : 0 } } });
    }
    if (url.pathname === "/api/update-checks" && request.method() === "POST") return route.fulfill({ status: 202, json: { job_id: "discovery-job" } });
    if (url.pathname === "/api/update-checks/discovery-job") {
      jobPolls += 1;
      return route.fulfill({ json: jobPolls === 1
        ? { job_id: "discovery-job", scope: "new", status: "running" }
        : { job_id: "discovery-job", scope: "new", status: "completed", outcome: "partial_success", discovered_count: 2, processed_count: 2, added_count: 1, failed_count: 1 } });
    }
    return route.fulfill({ status: 404, json: { error: { message: "Not mocked" } } });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Find new professors" }).click();
  await expect(page.getByRole("button", { name: "Checking for new professors…" })).toBeDisabled();
  await expect(page.getByRole("status")).toContainText("Added 1 new professor; 1 could not be added", { timeout: 5_000 });
  await expect(page.getByRole("link", { name: "New Professor" })).toBeVisible();
  await expect(page.locator("progress")).toHaveCount(0);
});
