import { forward } from "@/lib/proxy";

// Read at request time so one image runs anywhere and the key is never inlined into a bundle.
async function handle(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return forward(request, path, {
    url: process.env.API_URL ?? "http://api:8000",
    key: process.env.API_KEY || undefined,
  });
}

export { handle as DELETE, handle as GET, handle as PATCH, handle as POST };
