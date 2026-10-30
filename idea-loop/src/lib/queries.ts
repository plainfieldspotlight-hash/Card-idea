import { prisma } from "@/lib/db";

/** Options every idea form needs: goals to pick from, known sources and tags for autocomplete. */
export async function formOptions() {
  const [goals, sources, tags] = await Promise.all([
    prisma.goal.findMany({ where: { status: { not: "done" } }, orderBy: { name: "asc" }, select: { id: true, name: true } }),
    prisma.source.findMany({ orderBy: { title: "asc" }, select: { title: true } }),
    prisma.tag.findMany({ orderBy: { name: "asc" }, select: { id: true, name: true } }),
  ]);
  return { goals, sources, tags };
}
