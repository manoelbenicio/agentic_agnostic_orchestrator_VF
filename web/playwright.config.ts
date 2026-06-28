import { defineConfig, devices } from "@playwright/test";

const uiBaseURL = process.env.UI_BASE ?? "http://127.0.0.1:13000";
const apiBaseURL =
  process.env.API_BASE ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8090";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report" }],
  ],
  use: {
    baseURL: uiBaseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
  },
  webServer: {
    command: `NEXT_PUBLIC_API_URL=${apiBaseURL} NEXT_PUBLIC_AGENT_ID=w8:pS npm run dev -- --hostname 127.0.0.1 --port 13000`,
    url: uiBaseURL,
    reuseExistingServer: true,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
