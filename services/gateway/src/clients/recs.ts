/**
 * Client for recommendation-service. The gateway is stateless and never touches
 * the DB — it only speaks HTTP to the Python side.
 */
import type {
  CatalogResponse,
  ClassifyRequest,
  ClassifyResponse,
  RecommendationRequest,
  RecommendationResponse,
} from "../types.js";

export interface SseFrame {
  event: string;
  data: string;
}

export interface RecsClient {
  recommend(req: RecommendationRequest): Promise<RecommendationResponse>;
  stream(req: RecommendationRequest): AsyncGenerator<SseFrame>;
  universities(): Promise<CatalogResponse>;
  classify(body: ClassifyRequest): Promise<ClassifyResponse>;
}

/**
 * Parse a raw text/event-stream buffer into frames. Exported for unit testing.
 * Frames are separated by a blank line; `event:` and `data:` lines are joined.
 */
export function parseSse(buffer: string): SseFrame[] {
  const frames: SseFrame[] = [];
  for (const block of buffer.split("\n\n")) {
    const trimmed = block.trim();
    if (!trimmed) continue;
    let event = "message";
    const dataLines: string[] = [];
    for (const line of trimmed.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    frames.push({ event, data: dataLines.join("\n") });
  }
  return frames;
}

async function* streamFrames(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<SseFrame> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const [frame] = parseSse(block);
      if (frame) yield frame;
    }
  }
  const [frame] = parseSse(buffer);
  if (frame) yield frame;
}

export function createRecsClient(baseUrl: string): RecsClient {
  return {
    async recommend(req: RecommendationRequest): Promise<RecommendationResponse> {
      const res = await fetch(`${baseUrl}/recommend`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(req),
      });
      if (!res.ok) {
        throw new Error(`recommendation-service returned ${res.status}`);
      }
      return (await res.json()) as RecommendationResponse;
    },

    async universities(): Promise<CatalogResponse> {
      const res = await fetch(`${baseUrl}/universities`);
      if (!res.ok) {
        throw new Error(`recommendation-service returned ${res.status}`);
      }
      return (await res.json()) as CatalogResponse;
    },

    async *stream(req: RecommendationRequest): AsyncGenerator<SseFrame> {
      const res = await fetch(`${baseUrl}/recommend/stream`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(req),
      });
      if (!res.ok || !res.body) {
        throw new Error(`recommendation-service stream returned ${res.status}`);
      }
      yield* streamFrames(res.body);
    },

    async classify(body: ClassifyRequest): Promise<ClassifyResponse> {
      const res = await fetch(`${baseUrl}/activities/classify`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        throw new Error(`recommendation-service returned ${res.status}`);
      }
      return (await res.json()) as ClassifyResponse;
    },
  };
}
