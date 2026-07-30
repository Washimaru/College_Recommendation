import { afterEach, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";
import { WebSocket, type RawData } from "ws";

import { buildServer } from "../src/server.js";
import type { RecsClient, SseFrame } from "../src/clients/recs.js";

const FINAL = { results: [], confidence: 0.9, stop_reason: "R1_converged", trace: [] };

function fakeRecs(): RecsClient {
  return {
    async recommend() {
      return FINAL as never;
    },
    async universities() {
      return { universities: [] };
    },
    async classify() {
      return { subjects: [] };
    },
    async *stream(): AsyncGenerator<SseFrame> {
      yield { event: "iteration", data: '{"iteration":0}' };
      yield { event: "final", data: JSON.stringify(FINAL) };
    },
  };
}

let app: FastifyInstance;
afterEach(async () => {
  if (app) await app.close();
});

async function collect(port: number, payload: unknown): Promise<SseFrame[]> {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/v1/recommendations/ws`);
  const frames: SseFrame[] = [];
  return await new Promise((resolve, reject) => {
    ws.on("open", () => ws.send(JSON.stringify(payload)));
    ws.on("message", (d: RawData) => frames.push(JSON.parse(d.toString())));
    ws.on("close", () => resolve(frames));
    ws.on("error", reject);
  });
}

describe("ws relay", () => {
  it("relays SSE frames and closes after final", async () => {
    app = await buildServer({ recsClient: fakeRecs() });
    await app.listen({ port: 0, host: "127.0.0.1" });
    const port = (app.server.address() as { port: number }).port;
    const frames = await collect(port, {
      profile: { gpa: 3.8, intended_major: "CS" },
    });
    expect(frames.map((f) => f.event)).toContain("final");
  });

  it("sends an error frame for an invalid request", async () => {
    app = await buildServer({ recsClient: fakeRecs() });
    await app.listen({ port: 0, host: "127.0.0.1" });
    const port = (app.server.address() as { port: number }).port;
    const frames = await collect(port, { profile: { gpa: 99 } });
    expect(frames[0]?.event).toBe("error");
  });
});
