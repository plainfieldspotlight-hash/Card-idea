import { Suspense } from "react";
import { connection } from "next/server";
import { prisma } from "@/lib/db";
import { PageHeader } from "@/components/page-header";
import { Placeholder } from "@/components/placeholder";

export default function LibraryPage() {
  return (
    <>
      <PageHeader title="Library" subtitle="All ideas, grouped by goal." />
      <Suspense fallback={<ListSkeleton />}>
        <SeededIdeas />
      </Suspense>
      <div className="mt-6">
        <Placeholder phase={2}>
          Filters for tag, source, applied, and archived. Tap a card to open its detail screen.
        </Placeholder>
      </div>
    </>
  );
}

async function SeededIdeas() {
  await connection(); // read fresh on every request
  const goals = await prisma.goal.findMany({
    orderBy: { createdAt: "asc" },
    include: {
      ideas: {
        where: { status: "active" },
        orderBy: { createdAt: "asc" },
        include: { source: true },
      },
    },
  });

  if (goals.length === 0) {
    return <p className="text-sm text-muted">No ideas yet.</p>;
  }

  return (
    <div className="space-y-6">
      {goals.map((goal) => (
        <section key={goal.id}>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">
            {goal.name}
          </h2>
          <ul className="space-y-2">
            {goal.ideas.map((idea) => (
              <li key={idea.id} className="rounded-2xl border border-border bg-card p-4">
                <p className="text-sm leading-relaxed">{idea.text}</p>
                {idea.source ? (
                  <p className="mt-2 text-xs text-muted">{idea.source.title}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
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
