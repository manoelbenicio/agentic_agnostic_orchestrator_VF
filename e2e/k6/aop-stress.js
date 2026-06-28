import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate } from "k6/metrics";

const apiBase = (__ENV.API_BASE || "http://127.0.0.1:8095").replace(/\/$/, "");
const uiBase = (__ENV.UI_BASE || "http://127.0.0.1:13000").replace(/\/$/, "");
const tenant = __ENV.K6_TENANT_ID || "k6-tenant";
const project = __ENV.K6_PROJECT_ID || "k6-project";
const agent = __ENV.K6_AGENT_ID || "k6-agent";
const profile = __ENV.AOP_K6_PROFILE || __ENV.K6_PROFILE || "smoke";
const configuredVus = Number(__ENV.AOP_K6_VUS || __ENV.K6_VUS || (profile === "stress" ? 20 : 3));
const configuredDuration = __ENV.AOP_K6_DURATION || __ENV.K6_DURATION || (profile === "stress" ? "2m" : "20s");

export const options = {
  scenarios: {
    smoke: {
      executor: "constant-vus",
      vus: configuredVus,
      duration: configuredDuration,
      gracefulStop: "10s",
    },
  },
  thresholds: {
    http_req_failed: [`rate<${__ENV.K6_ERROR_RATE_MAX || "0.05"}`],
    http_req_duration: [`p(95)<${__ENV.K6_P95_MS || "750"}`],
    checks: ["rate>0.95"],
    aop_ready_latency: [`p(95)<${__ENV.K6_READY_P95_MS || "500"}`],
    aop_write_latency: [`p(95)<${__ENV.K6_WRITE_P95_MS || "1000"}`],
    aop_contract_failures: ["rate<0.05"],
  },
};

const readyLatency = new Trend("aop_ready_latency");
const writeLatency = new Trend("aop_write_latency");
const contractFailures = new Rate("aop_contract_failures");

function headers(extra = {}) {
  return {
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Agent-Id": agent,
      "X-AOP-Consumer": agent,
      ...extra,
    },
    timeout: "10s",
  };
}

function record(name, response, expectedStatuses = [200]) {
  const ok = expectedStatuses.includes(response.status);
  contractFailures.add(!ok);
  check(response, {
    [`${name} status ${expectedStatuses.join("|")}`]: () => ok,
  });
  return ok;
}

export function setup() {
  const health = http.get(`${apiBase}/health/ready`, headers());
  record("setup health ready", health, [200]);

  const ui = http.get(uiBase, { timeout: "15s" });
  record("setup frontend", ui, [200]);

  const llmHealth = http.get(`${apiBase}/llm/health`, headers());
  const ragHealth = http.get(`${apiBase}/rag/health`, headers());

  return {
    runId: `${Date.now()}`,
    llmEnabled: llmHealth.status === 200,
    ragEnabled: ragHealth.status === 200,
  };
}

export default function (data) {
  const suffix = `${data.runId}-${__VU}-${__ITER}`;

  const ready = http.get(`${apiBase}/health/ready`, headers());
  readyLatency.add(ready.timings.duration);
  record("health ready", ready, [200]);

  record("frontend dashboard", http.get(uiBase, { timeout: "15s" }), [200]);
  record("projects list", http.get(`${apiBase}/projects`, headers()), [200]);
  record("tasks board", http.get(`${apiBase}/tasks`, headers()), [200]);
  record("inbox unread count", http.get(`${apiBase}/inbox/unread-count`, headers()), [200]);
  if (data.llmEnabled) {
    record("llm gateway health", http.get(`${apiBase}/llm/health`, headers()), [200]);
  }
  if (data.ragEnabled) {
    record("rag health", http.get(`${apiBase}/rag/health`, headers()), [200]);
  }

  const tokenCost = http.post(
    `${apiBase}/finops/costs/token`,
    JSON.stringify({
      tenant_id: tenant,
      project_id: project,
      issue_id: `issue-${suffix}`,
      agent_id: agent,
      runtime_id: `runtime-${__VU}`,
      input_tokens: 12,
      output_tokens: 8,
      input_token_price_usd: "0.000001",
      output_token_price_usd: "0.000002",
      model: "glm-5.2",
      trace_id: `trace-${suffix}`,
    }),
    headers(),
  );
  writeLatency.add(tokenCost.timings.duration);
  record("finops token write", tokenCost, [200]);

  const trace = http.post(
    `${apiBase}/tracing/events`,
    JSON.stringify({
      trace_id: `trace-${suffix}`,
      layer: "l1_execution",
      signal_type: "burn",
      tenant_id: tenant,
      project_id: project,
      issue_id: `issue-${suffix}`,
      agent_id: agent,
      runtime_id: `runtime-${__VU}`,
      message: "k6 stress event",
      token_burn: 20,
      seat_seconds: 1,
    }),
    headers(),
  );
  writeLatency.add(trace.timings.duration);
  record("tracing event write", trace, [200]);

  const rollup = http.get(`${apiBase}/finops/projects/${tenant}/${project}/rollup`, headers());
  record("finops rollup", rollup, [200]);

  const task = http.post(
    `${apiBase}/tasks`,
    JSON.stringify({
      task_id: `k6-task-${suffix}`,
      tenant_id: tenant,
      project_id: project,
      issue_id: `issue-${suffix}`,
      assignee_runtime: `runtime-${__VU}`,
      prompt: "k6 contract dispatch",
      operation_mode: __ITER % 2 === 0 ? "terminal" : "socket",
      seat_seconds: 1,
      timeout_seconds: 1,
    }),
    headers(),
  );
  writeLatency.add(task.timings.duration);
  record("task dispatch contract", task, [200]);

  if (data.ragEnabled && __ITER % 5 === 0) {
    const rag = http.post(
      `${apiBase}/rag/query`,
      JSON.stringify({
        question: "Which API route reports health readiness?",
        top_k: 2,
      }),
      headers(),
    );
    record("rag query", rag, [200]);
  }

  sleep(Number(__ENV.K6_SLEEP_S || "0.2"));
}

export function handleSummary(data) {
  const output = {
    stdout: JSON.stringify(
      {
        apiBase,
        uiBase,
        profile,
        vus: configuredVus,
        duration: configuredDuration,
        metrics: {
          checks: data.metrics.checks,
          http_req_failed: data.metrics.http_req_failed,
          http_req_duration: data.metrics.http_req_duration,
          aop_ready_latency: data.metrics.aop_ready_latency,
          aop_write_latency: data.metrics.aop_write_latency,
          aop_contract_failures: data.metrics.aop_contract_failures,
        },
      },
      null,
      2,
    ),
  };
  if (__ENV.K6_SUMMARY_PATH) {
    output[__ENV.K6_SUMMARY_PATH] = JSON.stringify(data, null, 2);
  }
  return output;
}
