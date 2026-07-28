import { afterEach, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";

import { buildServer } from "../src/server.js";
import type { RecsClient, SseFrame } from "../src/clients/recs.js";
import { parseSse } from "../src/clients/recs.js";
import type { RecommendationResponse } from "../src/types.js";

const FIXTURE: RecommendationResponse = {
  results: [
    { university_id: "u1", name: "Alpha U", score: 0.91, rationale: "Great fit." },
  ],
  confidence: 0.9,
  stop_reason: "R1_converged",
  trace: [{ iteration: 0, top_ids: ["u1"], confidence: 0.9, stop_reason: "R1_converged" }],
};

function fakeRecs(): RecsClient {
  return {
    async recommend() {
      return FIXTURE;
    },
    async *stream(): AsyncGenerator<SseFrame> {
      yield { event: "iteration", data: JSON.stringify(FIXTURE.trace[0]) };
      yield { event: "final", data: JSON.stringify(FIXTURE) };
    },
  };
}

const VALID_BODY = {
  profile: { gpa: 3.8, sat: 1400, intended_major: "Computer Science" },
  top_k: 3,
};

let app: FastifyInstance;
afterEach(async () => {
  if (app) await app.close();
});

describe("gateway routes", () => {
  it("healthz returns ok", async () => {
    app = await buildServer({ recsClient: fakeRecs() });
    const res = await app.inject({ method: "GET", url: "/healthz" });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ status: "ok" });
  });

  it("returns a recommendation for a valid body", async () => {
    app = await buildServer({ recsClient: fakeRecs() });
    const res = await app.inject({ method: "POST", url: "/v1/recommendations", payload: VALID_BODY });
    expect(res.statusCode).toBe(200);
    expect(res.json().stop_reason).toBe("R1_converged");
    expect(res.json().results).toHaveLength(1);
  });

  it("rejects mbti as an unknown field", async () => {
    // Removed in contract v2.0.0; a stale client must fail loudly, not be ignored.
    app = await buildServer({ recsClient: fakeRecs() });
    const res = await app.inject({
      method: "POST",
      url: "/v1/recommendations",
      payload: { profile: { gpa: 3.8, mbti: "INTJ", intended_major: "CS" } },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe("invalid_request");
  });

  it("rejects an out-of-range culture preference", async () => {
    app = await buildServer({ recsClient: fakeRecs() });
    const res = await app.inject({
      method: "POST",
      url: "/v1/recommendations",
      payload: {
        profile: { gpa: 3.8, intended_major: "CS", culture_prefs: { collab: 1.7 } },
      },
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().error).toBe("invalid_request");
  });

  it("returns 502 when the upstream fails", async () => {
    const failing: RecsClient = {
      async recommend() {
        throw new Error("boom");
      },
      // eslint-disable-next-line require-yield
      async *stream(): AsyncGenerator<SseFrame> {
        throw new Error("boom");
      },
    };
    app = await buildServer({ recsClient: failing });
    const res = await app.inject({ method: "POST", url: "/v1/recommendations", payload: VALID_BODY });
    expect(res.statusCode).toBe(502);
  });
});

describe("parseSse", () => {
  it("parses event and data frames", () => {
    const frames = parseSse('event: iteration\ndata: {"a":1}\n\nevent: final\ndata: {"b":2}');
    expect(frames).toHaveLength(2);
    expect(frames[0]).toEqual({ event: "iteration", data: '{"a":1}' });
    expect(frames[1]).toEqual({ event: "final", data: '{"b":2}' });
  });

  it("skips empty blocks", () => {
    expect(parseSse("\n\n\n\n")).toHaveLength(0);
  });
});
