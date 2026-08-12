/**
 * @vitest-environment node
 *
 * The catalog proxy. An unreachable gateway must not reach the browse and
 * major-finder pages looking like an empty catalog - "no school teaches this"
 * is a very different claim from "we couldn't load the catalog".
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("GET /api/universities", () => {
  it("passes the catalog through", async () => {
    const catalog = { universities: [{ id: "mit", name: "MIT" }] };
    vi.stubGlobal("fetch", vi.fn(async () => Response.json(catalog)));

    const response = await GET();

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(catalog);
  });

  it("asks the gateway for the catalog", async () => {
    const fetchMock = vi.fn<(url: string) => Promise<Response>>(async () => Response.json({ universities: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await GET();

    expect(fetchMock.mock.calls[0][0]).toMatch(/\/v1\/universities$/);
  });

  it("answers 503 when the gateway is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );

    const response = await GET();

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "gateway_unreachable" });
  });

  it("answers 502 when the gateway answers with an error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 500 })));

    const response = await GET();

    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ error: "upstream_error" });
  });

  it("answers 503, not 200 with a broken body, when the response is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>hi</html>", { status: 200 })));

    const response = await GET();

    expect(response.status).toBe(503);
  });
});
