import { expect, test } from "@playwright/test";

function proposal(id, status = "pending") {
  return {
    id,
    job_id: `job-${id}`,
    professor_id: 7,
    status,
    old_values: { name: "Alice Systems", title: "Professor", email: "alice@illinois.edu", personal_homepage_url: "https://old.example.edu", research_summary: "Old summary", tags: ["Systems"], source_urls: ["https://ece.illinois.edu/alice"] },
    new_values: { name: "Alice Systems", title: "Professor", email: "alice@illinois.edu", personal_homepage_url: "https://new.example.edu", research_summary: "New summary", tags: ["Reliable AI"], source_urls: ["https://ece.illinois.edu/alice", "https://new.example.edu"] },
    publication_diff: { added: [{ title: "New Paper", year: 2026, venue: "ExampleConf" }], removed: [], proposed: [] },
    source_urls: ["https://new.example.edu"],
    confidence: 0.9,
  };
}

test("applies and rejects proposals only as whole-record decisions", async ({ page }) => {
  await page.route((url) => url.pathname.startsWith("/api/"), async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const id = Number(path.split("/")[3]);
    if (request.method() === "POST" && path.endsWith("/apply")) return route.fulfill({ json: proposal(id, "applied") });
    if (request.method() === "POST" && path.endsWith("/reject")) return route.fulfill({ json: proposal(id, "rejected") });
    if (request.method() === "GET" && path.startsWith("/api/update-proposals/")) return route.fulfill({ json: proposal(id) });
    return route.fulfill({ status: 404, json: { error: { message: "Not mocked" } } });
  });

  await page.goto("/updates/19");
  await expect(page.getByText("Old summary")).toBeVisible();
  await expect(page.getByText("New summary")).toBeVisible();
  await page.getByRole("button", { name: "Apply all changes" }).click();
  await expect(page.getByRole("status")).toContainText("proposal was applied");

  await page.goto("/updates/20");
  await page.getByRole("button", { name: "Reject update" }).click();
  await expect(page.getByRole("status")).toContainText("proposal was rejected");
});
