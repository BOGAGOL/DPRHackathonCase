export function contentSecurityPolicy(nonce: string): string {
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(nonce)) throw new Error("Invalid CSP nonce");
  return ["default-src 'self'", `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`, `style-src 'self' 'nonce-${nonce}'`, "img-src 'self' data:", "font-src 'self'", "connect-src 'self'", "frame-ancestors 'none'", "base-uri 'self'", "form-action 'self'", "object-src 'none'"].join("; ");
}
