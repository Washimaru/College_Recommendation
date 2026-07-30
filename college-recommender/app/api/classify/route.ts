/**
 * Server-side proxy to the gateway's activity classifier, same reasoning and
 * error discipline as /api/recommend: GATEWAY_URL stays server-side, the
 * gateway needs no CORS, and upstream failures are distinguished rather than
 * flattened (503 unreachable, 400 validation, 502 otherwise).
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
    upstream = await fetch(`${GATEWAY_URL}/v1/activities/classify`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    // The gateway is unreachable. This must not look like "nothing recognised".
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
