import { afterEach, describe, expect, it, vi } from "vitest";

import { createRecsClient } from "../src/clients/recs.js";
import type { RecommendationRequest } from "../src/types.js";

const REQ: RecommendationRequest = {
  profile: { gpa: 3.8, intended_major: "CS" },
  max_iterations: 5,
  top_k: 3,
};

afterEach(() => {
  vi.restoreAllMocks();
});

function sseBody(text: string): ReadableStream<Uint8Array> {
  const chunks = text.match(/[\s\S]{1,8}/g) ?? [text];
  const encoder = new TextEncoder();
  let i = 0;
  return new ReadableStream({
    pull(controller) {
      if (i < chunks.length) controller.enqueue(encoder.encode(chunks[i++]));
      else controller.close();
    },
  });
}

describe("createRecsClient.recommend", () => {
  it("returns the parsed response", async () => {
    const fixture = { results: [], confidence: 0.5, stop_reason: "R4_iteration_cap", trace: [] };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(fixture), { status: 200 })));
    const client = createRecsClient("http://svc");
    expect(await client.recommend(REQ)).toEqual(fixture);
  });

  it("throws on a non-2xx status", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 500 })));
    const client = createRecsClient("http://svc");
    await expect(client.recommend(REQ)).rejects.toThrow(/500/);
  });
});

describe("createRecsClient.stream", () => {
  it("yields frames split across chunk boundaries", async () => {
    const body = sseBody('event: iteration\ndata: {"i":0}\n\nevent: final\ndata: {"done":true}\n\n');
    vi.stubGlobal("fetch", vi.fn(async () => new Response(body, { status: 200 })));
    const client = createRecsClient("http://svc");
    const frames = [];
    for await (const f of client.stream(REQ)) frames.push(f);
    expect(frames.map((f) => f.event)).toEqual(["iteration", "final"]);
  });

  it("throws when the stream response is not ok", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 503 })));
    const client = createRecsClient("http://svc");
    await expect(async () => {
      for await (const _ of client.stream(REQ)) void _;
    }).rejects.toThrow(/503/);
  });
});
