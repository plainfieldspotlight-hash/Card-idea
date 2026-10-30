import { connection } from "next/server";
import { prisma } from "@/lib/db";

// Serves uploaded cover images stored in the database:
// /images/goal/<id>, /images/tag/<id> and /images/area/<id>.
export async function GET(_req: Request, ctx: RouteContext<"/images/[kind]/[id]">) {
  await connection();
  const { kind, id } = await ctx.params;

  const row =
    kind === "goal"
      ? await prisma.goal.findUnique({ where: { id }, select: { imageData: true, imageMime: true } })
      : kind === "tag"
        ? await prisma.tag.findUnique({ where: { id }, select: { imageData: true, imageMime: true } })
        : kind === "area"
          ? await prisma.area.findUnique({ where: { id }, select: { imageData: true, imageMime: true } })
          : null;

  if (!row?.imageData) return new Response("Not found", { status: 404 });

  return new Response(new Uint8Array(row.imageData), {
    headers: {
      "Content-Type": row.imageMime ?? "application/octet-stream",
      "Cache-Control": "public, max-age=31536000, immutable",
    },
  });
}
