import { prisma } from "@/lib/db";

/** Options every idea form needs: goals to pick from, known sources and tags for autocomplete. */
export async function formOptions() {
  const [areas, goals, sources, tags] = await Promise.all([
    prisma.area.findMany({ orderBy: [{ sortOrder: "asc" }, { name: "asc" }], select: { id: true, name: true } }),
    prisma.goal.findMany({
      where: { status: { not: "done" } },
      orderBy: { name: "asc" },
      select: { id: true, name: true, areaId: true },
    }),
    prisma.source.findMany({ orderBy: { title: "asc" }, select: { title: true } }),
    prisma.tag.findMany({ orderBy: { name: "asc" }, select: { id: true, name: true } }),
  ]);
  return { areas, goals, sources, tags };
}
