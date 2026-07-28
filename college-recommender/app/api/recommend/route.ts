/**
 * Server-side proxy to the gateway.
 *
 * Deliberately not a direct browser fetch: it keeps GATEWAY_URL server-side,
 * avoids needing CORS on a gateway that has none, and gives one place to shape
 * upstream failures. Route Handlers are not cached by default, which is what we
 * want here.
 */
const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid_json" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${GATEWAY_URL}/v1/recommendations`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    // The gateway is unreachable. This must not look like "no results".
    return Response.json({ error: "gateway_unreachable" }, { status: 503 });
  }

  const payload = await upstream.json().catch(() => null);
  if (!upstream.ok) {
    return Response.json(
      { error: "upstream_error", status: upstream.status, details: payload },
      { status: upstream.status === 400 ? 400 : 502 },
    );
  }
  return Response.json(payload);
}
