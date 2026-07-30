import { afterEach, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";

import { buildServer } from "../src/server.js";
import type { RecsClient, SseFrame } from "../src/clients/recs.js";

function fakeRecs(overrides: Partial<RecsClient> = {}): RecsClient {
  return {
    async recommend() {
      throw new Error("not used");
    },
    async universities() {
      return { universities: [] };
    },
    async classify() {
      return { subjects: ["Computer Science"] };
    },
    // eslint-disable-next-line require-yield
    async *stream(): AsyncGenerator<SseFrame> {
      throw new Error("not used");
    },
    ...overrides,
  } as RecsClient;
}

let app: FastifyInstance;
afterEach(async () => {
  await app?.close();
});

describe("POST /v1/activities/classify", () => {
  it("returns the recognised subjects", async () => {
    app = await buildServer({ recsClient: fakeRecs() });

    const res = await app.inject({
      method: "POST",
      url: "/v1/activities/classify",
      payload: { name: "FIRST Robotics", kind: "competition" },
    });

    expect(res.statusCode).toBe(200);
    expect(res.json().subjects).toContain("Computer Science");
  });

  it("rejects a body with no name", async () => {
    app = await buildServer({ recsClient: fakeRecs() });

    const res = await app.inject({
      method: "POST",
      url: "/v1/activities/classify",
      payload: { kind: "club" },
    });

    expect(res.statusCode).toBe(400);
  });

  it("returns 502 when the upstream fails", async () => {
    app = await buildServer({
      recsClient: fakeRecs({
        async classify() {
          throw new Error("down");
        },
      }),
    });

    const res = await app.inject({
      method: "POST",
      url: "/v1/activities/classify",
      payload: { name: "robotics", kind: "club" },
    });

    expect(res.statusCode).toBe(502);
  });
});
