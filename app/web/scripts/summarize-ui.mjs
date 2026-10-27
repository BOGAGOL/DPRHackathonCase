import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
const raw = JSON.parse(readFileSync(".local/ui-results.json", "utf8"));
const results = [];
function visit(suite) { for (const spec of suite.specs || []) for (const test of spec.tests) { const result = test.results.at(-1); results.push({ scenario: spec.title, status: result.status, duration_ms: result.duration }); } for (const child of suite.suites || []) visit(child); }
for (const suite of raw.suites || []) visit(suite);
mkdirSync("evidence/access-control", { recursive: true });
const summary = { status: results.length && results.every(r => r.status === "passed") ? "PASSED" : "FAILED", scope: "Chromium frontend with synthetic API mocks; does not verify backend authorization, database TLS or OpenBao", tests: results, timestamp_utc: new Date().toISOString() };
writeFileSync("evidence/access-control/ui-tests.json", JSON.stringify(summary, null, 2));
console.log(`UI evidence: ${summary.status}, ${results.length} scenarios`);
