/**
 * @vitest-environment node
 *
 * The activity classifier proxy. The distinction it keeps is the one the UI
 * relies on: a 503 means the check never happened, which the form shows
 * differently from a successful check that recognised nothing.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

function jsonRequest(body: unknown): Request {
  return new Request("http://localhost:3000/api/classify", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

const ACTIVITY = { name: "robotics club", kind: "club" };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("POST /api/classify", () => {
  it("passes the recognised subjects through", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ subjects: ["Computer Science", "Engineering"] })),
    );

    const response = await POST(jsonRequest(ACTIVITY));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ subjects: ["Computer Science", "Engineering"] });
  });

  it("passes an empty result through unchanged - nothing recognised is an answer", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ subjects: [] })));

    const response = await POST(jsonRequest({ name: "Science Bowl", kind: "club" }));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ subjects: [] });
  });

  it("sends the activity to the gateway's classify endpoint", async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
      Response.json({ subjects: [] }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await POST(jsonRequest(ACTIVITY));

    const [url, init] = fetchMock.mock.calls[0];
    expect(init).toBeDefined();
    expect(url).toMatch(/\/v1\/activities\/classify$/);
    expect(JSON.parse(String(init!.body))).toEqual(ACTIVITY);
  });

  it("answers 400 when the request body is not JSON", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(
      new Request("http://localhost:3000/api/classify", { method: "POST", body: "{oops" }),
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("answers 503, not an empty subject list, when the gateway is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );

    const response = await POST(jsonRequest(ACTIVITY));

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "gateway_unreachable" });
  });

  it("keeps a 400 from the gateway a 400", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ error: "invalid" }, { status: 400 })),
    );

    const response = await POST(jsonRequest(ACTIVITY));

    expect(response.status).toBe(400);
  });

  it("reports any other upstream failure as 502", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ error: "boom" }, { status: 502 })),
    );

    const response = await POST(jsonRequest(ACTIVITY));

    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({ error: "upstream_error", status: 502 });
  });
});
