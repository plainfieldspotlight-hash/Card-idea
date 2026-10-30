import { Suspense } from "react";
import { connection } from "next/server";
import Link from "next/link";
import { prisma } from "@/lib/db";
import { createGoal } from "@/lib/actions";
import { PageHeader } from "@/components/page-header";
import { Card, Chip, Field, Input, Notice } from "@/components/ui";
import { SubmitButton } from "@/components/submit-button";

export default function GoalsPage(props: PageProps<"/goals">) {
  return (
    <>
      <PageHeader title="Goals" subtitle="What the ideas are for." />
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

  const goals = await prisma.goal.findMany({
    orderBy: [{ status: "asc" }, { createdAt: "asc" }],
    include: {
      ideas: { where: { status: "active" }, select: { appliedCount: true } },
    },
  });

  return (
    <>
      {error ? <Notice tone="error">{error}</Notice> : null}

      {goals.length === 0 ? (
        <p className="mb-6 text-sm text-muted">No goals yet. Add the first one below.</p>
      ) : (
        <ul className="mb-8 space-y-2">
          {goals.map((goal) => {
            const linked = goal.ideas.length;
            const applied = goal.ideas.filter((i) => i.appliedCount > 0).length;
            return (
              <li key={goal.id}>
                <Link
                  href={`/goals/${goal.id}/edit`}
                  className={`block rounded-2xl border border-border bg-card p-4 transition-colors hover:border-accent/60 ${
                    goal.status !== "active" ? "opacity-60" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium">{goal.name}</p>
                      {goal.description ? <p className="mt-0.5 text-xs text-muted">{goal.description}</p> : null}
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
                </Link>
              </li>
            );
          })}
        </ul>
      )}

      <Card>
        <h2 className="mb-3 text-sm font-semibold">New goal</h2>
        <form action={createGoal} className="space-y-3">
          <Field label="Name" htmlFor="goal-name">
            <Input id="goal-name" name="name" required placeholder="Lead a treasury team well" />
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
