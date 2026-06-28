import {
  expect,
  request,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const apiBaseURL =
  process.env.API_BASE ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8090";
const tenantId = `playwright-${Date.now()}`;
const agentId = process.env.NEXT_PUBLIC_AGENT_ID ?? "w8:pS";

type SeedData = {
  inboxTitle: string;
  issueTitle: string;
};

let api: APIRequestContext;
let seed: SeedData;

async function expectNoFrameworkOverlay(page: Page) {
  await expect(
    page.getByText(/Unhandled Runtime Error|Application error|Build Error|Next\.js/i),
  ).toHaveCount(0);
}

async function expectMeaningfulShell(page: Page) {
  await expect(page.getByRole("link", { name: /Dashboard/i })).toBeVisible();
  await expect(page.getByText("AOP Control")).toBeVisible();
}

test.beforeAll(async ({ playwright }) => {
  api = await request.newContext({
    baseURL: apiBaseURL,
    extraHTTPHeaders: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Agent-Id": agentId,
    },
  });

  const health = await api.get("/health/ready");
  expect(health.status(), `control-plane must be reachable at ${apiBaseURL}`).toBeLessThan(600);

  seed = {
    inboxTitle: `Playwright inbox ${Date.now()}`,
    issueTitle: `Playwright issue ${Date.now()}`,
  };

  const inbox = await api.post("/inbox", {
    data: {
      tenant_id: tenantId,
      type: "issue_assigned",
      title: seed.inboxTitle,
      message: "Created by Playwright real E2E automation.",
    },
  });
  expect(inbox.status(), await inbox.text()).toBe(201);

  const issue = await api.post("/issues", {
    data: {
      tenant_id: tenantId,
      project_id: "playwright-project",
      title: seed.issueTitle,
      description: "Created by Playwright real E2E automation.",
      priority: "high",
      assignee_runtime: agentId,
      operation_mode: "terminal",
      metadata: { created_by: agentId, source: "playwright" },
    },
  });
  expect(issue.status(), await issue.text()).toBe(201);
});

test.afterAll(async () => {
  await api?.dispose();
});

test.beforeEach(async ({ page }) => {
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];

  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });

  await page.addInitScript(() => {
    window.localStorage.setItem("aop-playwright-run", "true");
  });

  await page.exposeFunction("__aopConsoleErrors", () => consoleErrors);
  await page.exposeFunction("__aopPageErrors", () => pageErrors);
});

test.afterEach(async ({ page }) => {
  const consoleErrors = (await page.evaluate(async () => {
    return await (
      window as unknown as { __aopConsoleErrors: () => Promise<string[]> }
    ).__aopConsoleErrors();
  })) as string[];
  const pageErrors = (await page.evaluate(async () => {
    return await (
      window as unknown as { __aopPageErrors: () => Promise<string[]> }
    ).__aopPageErrors();
  })) as string[];

  expect(pageErrors, "page runtime errors").toEqual([]);
  expect(
    consoleErrors.filter((entry) => !entry.includes("Failed to load resource")),
    "console errors",
  ).toEqual([]);
});

test("dashboard renders live shell, task board, and command palette navigation", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Agnostic Orchestration Platform|AOP/);
  await expectMeaningfulShell(page);
  await expectNoFrameworkOverlay(page);

  await expect(
    page.getByRole("heading", { name: "Agnostic Orchestration Platform" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "OTTL Task Tracker" })).toBeVisible();
  await expect(page.getByText(/\d+ tasks/i)).toBeVisible({ timeout: 15_000 });

  await page.keyboard.press(process.platform === "darwin" ? "Meta+K" : "Control+K");
  const searchDialog = page.getByRole("dialog");
  await expect(searchDialog).toBeVisible();
  await page.getByPlaceholder("Digite para buscar...").fill("Inbox");
  await searchDialog.getByRole("link", { name: /Inbox/i }).click();

  await expect(page).toHaveURL(/\/inbox$/);
  await expect(page.getByRole("heading", { name: "Inbox", exact: true })).toBeVisible();
});

test("inbox page reads real API data and marks a seeded event as read", async ({ page }) => {
  await page.goto("/inbox");
  await expectMeaningfulShell(page);
  await expectNoFrameworkOverlay(page);
  await expect(page.getByRole("heading", { name: "Inbox", exact: true })).toBeVisible();

  await page.getByRole("tab", { name: /All Events/i }).click();
  await expect(page.getByText(seed.inboxTitle)).toBeVisible({ timeout: 15_000 });

  const eventHeading = page.getByRole("heading", { name: seed.inboxTitle, exact: true });
  const eventCard = eventHeading.locator("../..");
  await eventCard.getByRole("button").click();

  await page.getByRole("tab", { name: "Read", exact: true }).click();
  await expect(page.getByText(seed.inboxTitle)).toBeVisible({ timeout: 15_000 });
});

test("my issues page filters live issue data across scopes", async ({ page }) => {
  await page.goto("/my-issues");
  await expectMeaningfulShell(page);
  await expectNoFrameworkOverlay(page);
  await expect(page.getByRole("heading", { name: "Minhas Issues" })).toBeVisible();

  await expect(page.getByText(seed.issueTitle)).toBeVisible({ timeout: 15_000 });

  await page.getByRole("tab", { name: /Assigned to me/i }).click();
  await expect(page.getByText(seed.issueTitle)).toBeVisible({ timeout: 15_000 });

  await page.getByRole("tab", { name: /Created by me/i }).click();
  await expect(page.getByText(seed.issueTitle)).toBeVisible({ timeout: 15_000 });
});
