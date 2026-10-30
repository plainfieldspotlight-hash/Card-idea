import { Suspense } from "react";
import { connection } from "next/server";
import Link from "next/link";
import { prisma } from "@/lib/db";
import { PageHeader } from "@/components/page-header";
import { IdeaCard } from "@/components/idea-card";
import { Select } from "@/components/ui";
import { SubmitButton } from "@/components/submit-button";
import { Cover } from "@/components/cover";
import { imageSrc } from "@/lib/cover";

type Filters = {
  tag: string;
  source: string;
  applied: "" | "yes" | "no";
  archived: "" | "1";
};

function readFilters(params: Record<string, string | string[] | undefined>): Filters {
  const one = (k: string) => (typeof params[k] === "string" ? (params[k] as string) : "");
  const applied = one("applied");
  return {
    tag: one("tag"),
    source: one("source"),
    applied: applied === "yes" || applied === "no" ? applied : "",
    archived: one("archived") === "1" ? "1" : "",
  };
}

export default function LibraryPage(props: PageProps<"/library">) {
  return (
    <>
      <PageHeader title="Library" subtitle="All ideas, grouped by goal." />
      <Suspense fallback={<ListSkeleton />}>
        <Library searchParams={props.searchParams} />
      </Suspense>
    </>
  );
}

async function Library({ searchParams }: { searchParams: PageProps<"/library">["searchParams"] }) {
  await connection();
  const filters = readFilters(await searchParams);
  const active = Object.values(filters).some(Boolean);

  const [tags, sources, ideas] = await Promise.all([
    prisma.tag.findMany({
      orderBy: { name: "asc" },
      select: { id: true, name: true, imageUrl: true, imageData: true, updatedAt: true, _count: { select: { ideas: true } } },
    }),
    prisma.source.findMany({ orderBy: { title: "asc" }, select: { id: true, title: true } }),
    prisma.idea.findMany({
      where: {
        status: filters.archived ? undefined : "active",
        ...(filters.tag ? { tags: { some: { tag: { name: filters.tag } } } } : {}),
        ...(filters.source ? { sourceId: filters.source } : {}),
        ...(filters.applied === "yes" ? { appliedCount: { gt: 0 } } : {}),
        ...(filters.applied === "no" ? { appliedCount: 0 } : {}),
      },
      orderBy: [{ status: "asc" }, { createdAt: "desc" }],
      include: {
        source: { select: { title: true } },
        goal: { select: { id: true, name: true, imageUrl: true, imageData: true, updatedAt: true } },
        tags: { include: { tag: { select: { name: true } } } },
      },
    }),
  ]);

  // Group by goal, keeping goal order stable and "No goal" last.
  const groups = new Map<string, { name: string; goal: (typeof ideas)[number]["goal"]; ideas: typeof ideas }>();
  for (const idea of ideas) {
    const key = idea.goal?.id ?? "__none";
    const name = idea.goal?.name ?? "No goal";
    if (!groups.has(key)) groups.set(key, { name, goal: idea.goal, ideas: [] });
    groups.get(key)!.ideas.push(idea);
  }
  const ordered = Array.from(groups.entries()).sort(([a], [b]) =>
    a === "__none" ? 1 : b === "__none" ? -1 : 0,
  );

  return (
    <>
      {tags.length ? (
        <section className="mb-6">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Topics</h2>
            <Link href="/topics" className="text-xs text-muted hover:text-foreground">
              All topics
            </Link>
          </div>
          <ul className="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-1">
            {tags.map((t) => (
              <li key={t.id} className="w-28 shrink-0 snap-start">
                <Link
                  href={`/library?tag=${encodeURIComponent(t.name)}`}
                  className={`block overflow-hidden rounded-xl border transition-colors hover:border-accent/60 ${
                    filters.tag === t.name ? "border-accent" : "border-border"
                  }`}
                >
                  <Cover name={t.name} src={imageSrc("tag", t)} className="aspect-square w-full" />
                  <div className="bg-card px-2 py-1.5">
                    <p className="truncate text-xs font-medium">#{t.name}</p>
                    <p className="text-[11px] text-muted tabular-nums">{t._count.ideas} {t._count.ideas === 1 ? "idea" : "ideas"}</p>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <form method="get" className="mb-6 grid grid-cols-2 gap-2">
        <Select name="tag" defaultValue={filters.tag} aria-label="Tag">
          <option value="">Any tag</option>
          {tags.map((t) => (
            <option key={t.name} value={t.name}>
              #{t.name}
            </option>
          ))}
        </Select>
        <Select name="source" defaultValue={filters.source} aria-label="Source">
          <option value="">Any source</option>
          {sources.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title}
            </option>
          ))}
        </Select>
        <Select name="applied" defaultValue={filters.applied} aria-label="Applied">
          <option value="">Applied or not</option>
          <option value="yes">Applied</option>
          <option value="no">Not yet applied</option>
        </Select>
        <Select name="archived" defaultValue={filters.archived} aria-label="Archived">
          <option value="">Hide archived</option>
          <option value="1">Include archived</option>
        </Select>
        <SubmitButton className="col-span-2" variant="secondary" pendingLabel="Filtering…">
          Filter
        </SubmitButton>
        {active ? (
          <Link href="/library" className="col-span-2 text-center text-xs text-muted hover:text-foreground">
            Clear filters
          </Link>
        ) : null}
      </form>

      {ideas.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-border bg-card p-5 text-center text-sm text-muted">
          {active ? "Nothing matches these filters." : "No ideas yet."}{" "}
          <Link href="/add" className="text-accent underline-offset-2 hover:underline">
            Add one
          </Link>
          .
        </p>
      ) : (
        <div className="space-y-6">
          {ordered.map(([key, group]) => (
            <section key={key}>
              <h2 className="mb-2 flex items-center justify-between gap-3 text-sm font-semibold uppercase tracking-wide text-muted">
                <span className="flex items-center gap-2">
                  {group.goal ? (
                    <Cover name={group.goal.name} src={imageSrc("goal", group.goal)} size="sm" className="h-7 w-7 rounded-lg" />
                  ) : null}
                  {group.goal ? (
                    <Link href={`/goals/${group.goal.id}/edit`} className="hover:text-foreground">
                      {group.name}
                    </Link>
                  ) : (
                    <span>{group.name}</span>
                  )}
                </span>
                <span className="text-xs font-normal normal-case tabular-nums">{group.ideas.length}</span>
              </h2>
              <ul className="space-y-2">
                {group.ideas.map((idea) => (
                  <IdeaCard key={idea.id} idea={idea} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-2">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-20 animate-pulse rounded-2xl border border-border bg-card" />
      ))}
    </div>
  );
}
