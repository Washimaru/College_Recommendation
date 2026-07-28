/**
 * WebSocket relay: SSE from recommendation-service -> WS frames to the client.
 * Breaks the relay on the `final` event, mirroring gateway/src/clients/recs.ts.
 */
import type { FastifyInstance } from "fastify";

import type { RecsClient } from "./clients/recs.js";
import { RecommendationRequestSchema } from "./types.js";

export function registerWs(app: FastifyInstance, recs: RecsClient): void {
  app.get("/v1/recommendations/ws", { websocket: true }, (socket) => {
    socket.on("message", async (raw: Buffer) => {
      let req;
      try {
        req = RecommendationRequestSchema.parse(JSON.parse(raw.toString()));
      } catch (err) {
        socket.send(JSON.stringify({ event: "error", data: String(err) }));
        socket.close();
        return;
      }
      try {
        for await (const frame of recs.stream(req)) {
          socket.send(JSON.stringify(frame));
          if (frame.event === "final") break;
        }
      } catch (err) {
        socket.send(JSON.stringify({ event: "error", data: String(err) }));
      } finally {
        socket.close();
      }
    });
  });
}
