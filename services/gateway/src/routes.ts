/**
 * REST routes. The gateway validates with zod (src/types.ts) and delegates to
 * recommendation-service. It holds no state and never accesses the DB.
 */
import type { FastifyInstance } from "fastify";

import type { RecsClient } from "./clients/recs.js";
import { RecommendationRequestSchema } from "./types.js";

export function registerRoutes(app: FastifyInstance, recs: RecsClient): void {
  app.get("/healthz", async () => ({ status: "ok" }));

  app.post("/v1/recommendations", async (request, reply) => {
    const parsed = RecommendationRequestSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({
        error: "invalid_request",
        details: parsed.error.flatten(),
      });
    }
    try {
      const result = await recs.recommend(parsed.data);
      return reply.status(200).send(result);
    } catch (err) {
      request.log.error(err);
      return reply.status(502).send({ error: "upstream_error" });
    }
  });
}
