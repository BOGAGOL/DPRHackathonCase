import { createServer } from "node:https";
import { readFileSync } from "node:fs";
import next from "next";

const hostname = process.env.WEB_HOST || "127.0.0.1";
const port = Number(process.env.WEB_PORT || "3443");
if (!process.env.TLS_CERT_FILE || !process.env.TLS_KEY_FILE) throw new Error("TLS_CERT_FILE and TLS_KEY_FILE must point to Module A's certificate and key. HTTP fallback is disabled.");
const app = next({ dev: false, hostname, port });
await app.prepare();
const handler = app.getRequestHandler();
createServer({ cert: readFileSync(process.env.TLS_CERT_FILE), key: readFileSync(process.env.TLS_KEY_FILE) }, (request, response) => {
  // Never print request URLs: the exact-match API uses a sensitive query string.
  handler(request, response);
}).listen(port, hostname, () => console.log(`DPR service web ready on https://localhost:${port}`));
