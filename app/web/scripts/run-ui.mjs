import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";

const raw = path.resolve(".local/ui-results.json");
if (existsSync(raw)) unlinkSync(raw);
const result = spawnSync(process.execPath, ["node_modules/@playwright/test/cli.js", "test", ...process.argv.slice(2)], { stdio: "inherit", env: process.env });
let report;
try {
  if (!existsSync(raw)) throw new Error("No machine report");
  await import("./summarize-ui.mjs");
  report = JSON.parse(readFileSync("evidence/access-control/ui-tests.json", "utf8"));
} catch {
  report = { status: "FAILED", scope: "UI runner did not produce a valid machine report", tests: [] };
}
if (result.status !== 0 || !report.tests?.length) report.status = "FAILED";
for (const directory of ["evidence/access-control", "../evidence/access-control"]) {
  mkdirSync(directory, { recursive: true });
  writeFileSync(path.join(directory, directory.startsWith("../") ? "browser-tests.json" : "ui-tests.json"), JSON.stringify(report, null, 2));
}
process.exitCode = report.status === "PASSED" && result.status === 0 ? 0 : 1;
