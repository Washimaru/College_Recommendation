import { buildServer } from "./server.js";

const PORT = Number(process.env.PORT ?? 8000);

async function main(): Promise<void> {
  const app = await buildServer();
  await app.listen({ host: "0.0.0.0", port: PORT });
  // eslint-disable-next-line no-console
  console.log(`gateway listening on :${PORT}`);
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error(err);
  process.exit(1);
});
