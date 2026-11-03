import { expect, test } from "@playwright/test";

// One journey through the real stack, with no Google API key: upload a file, watch it finish, open it,
// find it by keyword. Correcting a value needs an extracted invoice, which needs the model; that path is
// covered by the component tests and by the manual run with a real key (docs/testing.md).
test("upload a spreadsheet, see it processed, open it and find it by keyword", async ({ page }) => {
  const token = `zebra${Date.now()}`;
  const csv = `invoice_number,supplier,total\nINV-1,${token} Traders,120.00\nINV-2,${token} Traders,80.00\n`;
  const name = `e2e-${token}.csv`;

  await page.goto("/upload");
  await page.getByLabel("Choose files").setInputFiles({ name, mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByText(name)).toBeVisible();
  await page.getByRole("button", { name: /^Upload 1 file/ }).click();

  // The result row replaces the progress bar, with a link to the document.
  await expect(page.getByText("Accepted")).toBeVisible();
  await page.getByRole("link", { name: "View", exact: true }).click();

  // Processing finishes by itself: the page polls and the badge changes. Failed counts as finished here: this
  // journey is about reading, indexing and finding the file, and extraction depends on the model setup.
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.locator("[data-status]").first()).toHaveText(/Completed|Needs review|Failed/, { timeout: 60_000 });
  await expect(page.getByRole("list", { name: "Processing steps" })).toContainText("Reading the file");
  // A spreadsheet has no viewer: it is offered as a download.
  await expect(page.getByText(/cannot be previewed/)).toBeVisible();

  // The text was indexed when the file was read, so keyword search finds it.
  await page.goto(`/search?q=${token}&mode=keyword`);
  await expect(page.getByRole("link", { name })).toBeVisible({ timeout: 30_000 });

  // And the list shows it.
  await page.goto("/documents");
  await expect(page.getByRole("link", { name })).toBeVisible();
});
