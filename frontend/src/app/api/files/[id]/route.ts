import { forwardFile } from "@/lib/proxy";

async function GET(request: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  return forwardFile(request, id, {
    url: process.env.API_URL ?? "http://api:8000",
    key: process.env.API_KEY || undefined,
  });
}

export { GET };
