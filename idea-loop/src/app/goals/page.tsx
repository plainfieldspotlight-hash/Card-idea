import { Suspense } from "react";
import { connection } from "next/server";
import { prisma } from "@/lib/db";
import { PageHeader } from "@/components/page-header";
import { Placeholder } from "@/components/placeholder";

export default function GoalsPage() {
  return (
    <>
      <PageHeader title="Goals" subtitle="What the ideas are for." />
      <Suspense fallback={<div className="h-20 animate-pulse rounded-2xl border border-border bg-card" />}>
        <GoalList />
      </Suspense>
      <div className="mt-6">
        <Placeholder phase={2}>Create and edit goals here.</Placeholder>
      </div>
    </>
  );
}

async function GoalList() {
  await connection(); // read fresh on every request
  const goals = await prisma.goal.findMany({
    orderBy: { createdAt: "asc" },
    include: { _count: { select: { ideas: true } } },
  });

  if (goals.length === 0) return <p className="text-sm text-muted">No goals yet.</p>;

  return (
    <ul className="space-y-2">
      {goals.map((goal) => (
        <li key={goal.id} className="flex items-center justify-between rounded-2xl border border-border bg-card p-4">
          <div>
            <p className="font-medium">{goal.name}</p>
            {goal.description ? <p className="mt-0.5 text-xs text-muted">{goal.description}</p> : null}
          </div>
          <span className="ml-4 shrink-0 rounded-full bg-accent px-2.5 py-0.5 text-xs font-medium text-accent-foreground tabular-nums">
            {goal._count.ideas}
          </span>
        </li>
      ))}
    </ul>
  );
}
