import { afterEach, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";

import { buildServer } from "../src/server.js";
import type { RecsClient, SseFrame } from "../src/clients/recs.js";

const CATALOG = {
  universities: [
    {
      id: "alpha-u", unitid: null, name: "Alpha U", country: "USA", location: "CA",
      avg_gpa: 3.9, avg_sat: 1450, acceptance_rate: 0.15, net_price: 20000,
      sticker_tuition: 60000, enrollment: 8000, size: "medium",
      majors: ["Computer Science"],
      culture: { collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.8, spirit: 0.3, seminar: 0.6 },
      provenance: { avg_sat: "observed" },
    },
  ],
};

function fakeRecs(overrides: Partial<RecsClient> = {}): RecsClient {
  return {
    async recommend() {
      throw new Error("not used");
    },
    async *stream(): AsyncGenerator<SseFrame> {},
    async universities() {
      return CATALOG;
    },
    ...overrides,
  } as RecsClient;
}

let app: FastifyInstance;
afterEach(async () => {
  await app?.close();
});

describe("GET /v1/universities", () => {
  it("returns the catalog", async () => {
    app = await buildServer({ recsClient: fakeRecs() });

    const res = await app.inject({ method: "GET", url: "/v1/universities" });

    expect(res.statusCode).toBe(200);
    expect(res.json().universities[0].name).toBe("Alpha U");
  });

  it("returns 502 when the upstream fails", async () => {
    app = await buildServer({
      recsClient: fakeRecs({
        async universities() {
          throw new Error("upstream down");
        },
      }),
    });

    const res = await app.inject({ method: "GET", url: "/v1/universities" });

    expect(res.statusCode).toBe(502);
    expect(res.json().error).toBe("upstream_error");
  });
});
