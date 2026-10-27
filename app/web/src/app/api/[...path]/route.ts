import { forwardToBackend } from "@/lib/backend-proxy";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) { return forwardToBackend(request, (await context.params).path); }
export { proxy as GET, proxy as POST, proxy as PATCH, proxy as PUT, proxy as DELETE, proxy as HEAD, proxy as OPTIONS };
