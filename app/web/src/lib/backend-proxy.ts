const responseHeaders = { "Content-Type": "application/json", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'" };
function unavailable(status = 502) { return new Response(JSON.stringify({ detail: "Layanan sementara tidak tersedia." }), { status, headers: responseHeaders }); }

export function upstreamUrl(segments: string[], search: string, base: string): URL {
  const target = new URL(base);
  if (target.protocol !== "https:" || target.username || target.password || target.search || target.hash || target.pathname !== "/") throw new Error("Invalid HTTPS backend configuration");
  if (!segments.length || !["auth", "anggota", "analytics", "audit", "health"].includes(segments[0]) || segments.some(p => !/^[a-zA-Z0-9_.-]+$/.test(p) || [".", ".."].includes(p))) throw new Error("Invalid API path");
  target.pathname = "/" + segments.map(encodeURIComponent).join("/");
  target.search = search;
  return target;
}

export async function forwardToBackend(request: Request, segments: string[], fetcher: typeof fetch = fetch): Promise<Response> {
  try {
    const target = upstreamUrl(segments, new URL(request.url).search, process.env.API_INTERNAL_URL || "https://127.0.0.1:8100");
    const headers = new Headers();
    for (const name of ["content-type", "cookie", "origin", "x-csrf-token"]) { const value = request.headers.get(name); if (value) headers.set(name, value); }
    const method = request.method.toUpperCase();
    let body: ArrayBuffer | undefined;
    if (!["GET", "HEAD"].includes(method)) {
      const length = request.headers.get("content-length");
      if (length && (!/^\d+$/.test(length) || Number(length) > 32768)) return unavailable(413);
      body = await request.arrayBuffer();
      if (body.byteLength > 32768) return unavailable(413);
    }
    const upstream = await fetcher(target, { method, headers, body, redirect: "manual", cache: "no-store", signal: AbortSignal.timeout(15000) });
    if (upstream.status >= 300 && upstream.status < 400) return unavailable();
    const outputHeaders = new Headers(responseHeaders);
    const contentType = upstream.headers.get("content-type");
    if (contentType) outputHeaders.set("content-type", contentType);
    for (const name of ["x-request-id"]) { const value = upstream.headers.get(name); if (value) outputHeaders.set(name, value); }
    for (const cookie of upstream.headers.getSetCookie()) outputHeaders.append("set-cookie", cookie);
    return new Response([204, 304].includes(upstream.status) || method === "HEAD" ? null : upstream.body, { status: upstream.status, headers: outputHeaders });
  } catch {
    // Fetch errors can contain the complete lookup URL. Do not print or return them.
    return unavailable();
  }
}
