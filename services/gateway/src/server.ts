/** Assemble the Fastify app. Kept separate from index.ts so tests can build it
 * without binding a port. */
import Fastify, { type FastifyInstance } from "fastify";
import websocket from "@fastify/websocket";

import { createRecsClient, type RecsClient } from "./clients/recs.js";
import { registerRoutes } from "./routes.js";
import { registerWs } from "./ws.js";

export interface BuildOptions {
  recsClient?: RecsClient;
  recsUrl?: string;
}

export async function buildServer(opts: BuildOptions = {}): Promise<FastifyInstance> {
  const app = Fastify({ logger: false });
  const recs =
    opts.recsClient ??
    createRecsClient(opts.recsUrl ?? process.env.RECS_SERVICE_URL ?? "http://recommendation-service:8002");
  await app.register(websocket);
  await app.register(async (instance) => {
    registerRoutes(instance, recs);
    registerWs(instance, recs);
  });
  return app;
}
