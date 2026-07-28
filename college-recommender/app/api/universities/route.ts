/**
 * Server-side proxy for the catalog, same reasoning as /api/recommend:
 * GATEWAY_URL stays server-side and the gateway needs no CORS.
 */
const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:8000";

export async function GET() {
  try {
    const upstream = await fetch(`${GATEWAY_URL}/v1/universities`);
    if (!upstream.ok) {
      return Response.json({ error: "upstream_error" }, { status: 502 });
    }
    return Response.json(await upstream.json());
  } catch {
    return Response.json({ error: "gateway_unreachable" }, { status: 503 });
  }
}
