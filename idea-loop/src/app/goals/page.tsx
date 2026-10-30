import { Suspense } from "react";
import { connection } from "next/server";
import Link from "next/link";
import { prisma } from "@/lib/db";
import { createGoal } from "@/lib/actions";
import { imageSrc } from "@/lib/cover";
import { PageHeader } from "@/components/page-header";
import { Cover } from "@/components/cover";
import { Card, Chip, Field, Input, Notice, Select } from "@/components/ui";
import { SubmitButton } from "@/components/submit-button";

export default function GoalsPage(props: PageProps<"/goals">) {
  return (
    <>
      <PageHeader title="Goals" subtitle="What the ideas are for, by area of life." />
      <Suspense fallback={<div className="h-20 animate-pulse rounded-2xl border border-border bg-card" />}>
        <GoalList searchParams={props.searchParams} />
      </Suspense>
    </>
  );
}

async function GoalList({ searchParams }: { searchParams: PageProps<"/goals">["searchParams"] }) {
  await connection();
  const query = await searchParams;
  const error = typeof query.error === "string" ? query.error : null;

  const [areas, goals] = await Promise.all([
    prisma.area.findMany({
      orderBy: [{ sortOrder: "asc" }, { name: "asc" }],
      include: { _count: { select: { goals: true, ideas: true } } },
    }),
    prisma.goal.findMany({
      orderBy: [{ status: "asc" }, { createdAt: "asc" }],
      include: {
        area: { select: { id: true, name: true } },
        ideas: { where: { status: "active" }, select: { appliedCount: true } },
      },
    }),
  ]);

  // Goals grouped by area, in area order, with "No area" last.
  const sections = [
    ...areas.map((a) => ({ key: a.id, name: a.name, goals: goals.filter((g) => g.areaId === a.id) })),
    { key: "__none", name: "No area", goals: goals.filter((g) => !g.areaId) },
  ].filter((s) => s.goals.length > 0);

  return (
    <>
      {error ? <Notice tone="error">{error}</Notice> : null}

      <section className="mb-6">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Areas</h2>
          <Link href="/areas" className="text-xs text-muted hover:text-foreground">
            Manage areas
          </Link>
        </div>
        <ul className="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-1">
          {areas.map((a) => (
            <li key={a.id} className="w-28 shrink-0 snap-start">
              <Link
                href={`/areas/${a.id}`}
                className="block overflow-hidden rounded-xl border border-border transition-colors hover:border-accent/60"
              >
                <Cover name={a.name} src={imageSrc("area", a)} className="aspect-square w-full" />
                <div className="bg-card px-2 py-1.5">
                  <p className="truncate text-xs font-medium">{a.name}</p>
                  <p className="text-[11px] text-muted tabular-nums">
                    {a._count.goals} {a._count.goals === 1 ? "goal" : "goals"}
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      {sections.length === 0 ? (
        <p className="mb-6 text-sm text-muted">No goals yet. Add the first one below.</p>
      ) : (
        <div className="mb-8 space-y-6">
          {sections.map((section) => (
            <section key={section.key}>
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">{section.name}</h2>
              <ul className="space-y-2">
                {section.goals.map((goal) => {
                  const linked = goal.ideas.length;
                  const applied = goal.ideas.filter((i) => i.appliedCount > 0).length;
                  return (
                    <li key={goal.id}>
                      <Link
                        href={`/goals/${goal.id}/edit`}
                        className={`block overflow-hidden rounded-2xl border border-border bg-card transition-colors hover:border-accent/60 ${
                          goal.status !== "active" ? "opacity-60" : ""
                        }`}
                      >
                        <Cover name={goal.name} src={imageSrc("goal", goal)} className="aspect-[3/1] w-full" />
                        <div className="p-4">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="font-medium">{goal.name}</p>
                              {goal.description ? (
                                <p className="mt-0.5 text-xs text-muted">{goal.description}</p>
                              ) : null}
                            </div>
                            {goal.status !== "active" ? <Chip>{goal.status}</Chip> : null}
                          </div>
                          <div className="mt-3 flex gap-4 text-xs text-muted">
                            <span>
                              <span className="font-semibold text-foreground tabular-nums">{linked}</span> ideas
                            </span>
                            <span>
                              <span className="font-semibold text-foreground tabular-nums">{applied}</span> applied
                            </span>
                          </div>
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}

      <Card>
        <h2 className="mb-3 text-sm font-semibold">New goal</h2>
        <form action={createGoal} className="space-y-3">
          <Field label="Name" htmlFor="goal-name">
            <Input id="goal-name" name="name" required placeholder="Lead a treasury team well" />
          </Field>
          <Field label="Area" htmlFor="goal-area">
            <Select id="goal-area" name="areaId" defaultValue="">
              <option value="">No area</option>
              {areas.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Description" hint="optional" htmlFor="goal-description">
            <Input id="goal-description" name="description" placeholder="What done looks like" />
          </Field>
          <SubmitButton className="w-full">Add goal</SubmitButton>
        </form>
      </Card>
    </>
  );
}
