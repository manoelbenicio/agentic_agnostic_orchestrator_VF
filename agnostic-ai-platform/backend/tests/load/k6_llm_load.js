import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';

// --- Custom Metrics ---
const llmRequestDuration = new Trend('llm_request_duration', true);
const llmTokensProcessed = new Counter('llm_tokens_processed');
const llmTokensPerSecond = new Trend('llm_tokens_per_second');

// --- Configuration via Environment Variables ---
// Allow runtime overrides: k6 run -e BASE_URL=http://prod -e SCENARIO=load k6_llm_load.js
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_KEY = __ENV.API_KEY || 'sk-test-123';
const RUN_SCENARIO = __ENV.SCENARIO || 'smoke'; // Default execution to 'smoke' test

// --- Scenario Definitions ---
const scenarios = {
    // 1 VU for 30s to verify the script and basic functionality work
    smoke: {
        executor: 'constant-vus',
        vus: 1,
        duration: '30s',
    },
    // Normal load capacity: 50 VUs sustained over 5 minutes (ramping up and down)
    load: {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: [
            { duration: '1m', target: 50 },  // Ramp-up
            { duration: '3m', target: 50 },  // Sustained load
            { duration: '1m', target: 0 },   // Ramp-down
        ],
    },
    // High stress: 200 VUs sustained over 2 minutes
    stress: {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: [
            { duration: '30s', target: 200 }, // Rapid Ramp-up
            { duration: '1m', target: 200 },  // Sustained high stress
            { duration: '30s', target: 0 },   // Ramp-down
        ],
    },
    // Sudden surge: 0 to 100 VUs in 10s
    spike: {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: [
            { duration: '10s', target: 100 }, // Sudden spike
            { duration: '1m', target: 100 },  // Hold the spike
            { duration: '20s', target: 0 },   // Scale down gracefully
        ],
    },
};

export const options = {
    scenarios: {
        // Run only the single selected scenario from the env variable
        active_scenario: scenarios[RUN_SCENARIO],
    },
    thresholds: {
        // Non-negotiable Performance SLAs
        // p95 latency must be strictly less than 2 seconds (2000ms)
        http_req_duration: ['p(95)<2000'],
        llm_request_duration: ['p(95)<2000'],
        
        // Error rate must remain under 1%
        http_req_failed: ['rate<0.01'], 
    },
};

export default function () {
    const url = `${BASE_URL}/v1/chat/completions`;
    
    // We send a lightweight completion request so it doesn't skew network throughput limits
    const payload = JSON.stringify({
        model: 'gpt-3.5-turbo',
        messages: [
            { role: 'system', content: 'You are a helpful load-testing assistant.' },
            { role: 'user', content: 'Tell me a short, one-sentence joke about performance.' }
        ],
        max_tokens: 50
    });

    const params = {
        headers: {
            'Content-Type': 'application/json',
            'X-API-Key': API_KEY,
        },
        // We set a hard timeout so blocked connections are appropriately marked as failed
        timeout: '30s', 
    };

    const startTime = new Date().getTime();
    
    // Execute the POST request
    const res = http.post(url, payload, params);
    
    const endTime = new Date().getTime();
    const durationMs = endTime - startTime;

    // Validate the response
    const success = check(res, {
        'status is 200': (r) => r.status === 200,
        'has model in response': (r) => r.json('model') !== undefined,
        'has usage data': (r) => r.json('usage.total_tokens') !== undefined,
    });

    // Only record analytical metrics on successful runs to prevent skewing
    if (success) {
        llmRequestDuration.add(durationMs);
        
        const totalTokens = res.json('usage.total_tokens');
        if (totalTokens) {
            llmTokensProcessed.add(totalTokens);
            
            // Calculate strictly how many tokens were processed per second for this interaction
            const durationSeconds = durationMs / 1000.0;
            if (durationSeconds > 0) {
                const tps = totalTokens / durationSeconds;
                llmTokensPerSecond.add(tps);
            }
        }
    }

    // Think time / rate-limit buffer
    sleep(1);
}
