/**
 * @vitest-environment node
 *
 * The proxy's whole job is to distinguish failures the UI must not confuse:
 * an unreachable gateway is not "no schools matched", and a rejected profile
 * is not a server fault. Every branch here was untested until `app/**` was
 * added to the vitest include glob.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

function jsonRequest(body: unknown): Request {
  return new Request("http://localhost:3000/api/recommend", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

const PROFILE = { profile: { gpa: 3.8, intended_major: "Computer Science" } };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("POST /api/recommend", () => {
  it("passes a successful recommendation straight through", async () => {
    const upstream = { results: [{ name: "MIT" }], confidence: 0.9 };
    vi.stubGlobal("fetch", vi.fn(async () => Response.json(upstream)));

    const response = await POST(jsonRequest(PROFILE));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(upstream);
  });

  it("sends the body to the gateway's recommendations endpoint", async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
      Response.json({ results: [] }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await POST(jsonRequest(PROFILE));

    const [url, init] = fetchMock.mock.calls[0];
    expect(init).toBeDefined();
    expect(url).toMatch(/\/v1\/recommendations$/);
    expect(init!.method).toBe("POST");
    expect(JSON.parse(String(init!.body))).toEqual(PROFILE);
  });

  it("answers 400 when the request body is not JSON", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(
      new Request("http://localhost:3000/api/recommend", { method: "POST", body: "{oops" }),
    );

    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "invalid_json" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("answers 503, not an empty result, when the gateway is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );

    const response = await POST(jsonRequest(PROFILE));

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "gateway_unreachable" });
  });

  it("keeps a 400 from the gateway a 400, since the profile is what is wrong", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ error: "invalid_profile" }, { status: 400 })),
    );

    const response = await POST(jsonRequest(PROFILE));

    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ error: "upstream_error", status: 400 });
  });

  it("reports any other upstream failure as 502", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ error: "boom" }, { status: 500 })),
    );

    const response = await POST(jsonRequest(PROFILE));

    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({ status: 500 });
  });

  it("survives an upstream error whose body is not JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<html>502 Bad Gateway</html>", { status: 502 })),
    );

    const response = await POST(jsonRequest(PROFILE));

    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({ details: null });
  });
});
