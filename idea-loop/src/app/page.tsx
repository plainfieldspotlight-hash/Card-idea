import { Suspense } from "react";
import Link from "next/link";
import { connection } from "next/server";
import { prisma } from "@/lib/db";
import { PageHeader } from "@/components/page-header";
import { Placeholder } from "@/components/placeholder";

export default function TodayPage() {
  return (
    <>
      <PageHeader title="Today" subtitle="Ideas due for review." />
      <Suspense fallback={<DueSkeleton />}>
        <DueSummary />
      </Suspense>
      <div className="mt-6">
        <Placeholder phase={3}>
          The review loop: one card at a time with Used it, Not yet, and Archive.
        </Placeholder>
      </div>
    </>
  );
}

async function DueSummary() {
  await connection(); // "today" is request time, never build time
  const due = await prisma.idea.count({
    where: { status: "active", nextReviewAt: { lte: new Date() } },
  });

  if (due === 0) {
    return (
      <div className="rounded-2xl border border-border bg-card p-5">
        <p className="font-medium">Nothing due.</p>
        <p className="mt-1 text-sm text-muted">
          <Link href="/add" className="text-accent underline-offset-2 hover:underline">
            Add an idea
          </Link>{" "}
          or import a source.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-border bg-card p-5">
      <p className="text-3xl font-semibold tabular-nums">{due}</p>
      <p className="mt-1 text-sm text-muted">{due === 1 ? "idea is" : "ideas are"} due today.</p>
    </div>
  );
}

function DueSkeleton() {
  return <div className="h-24 animate-pulse rounded-2xl border border-border bg-card" />;
}
