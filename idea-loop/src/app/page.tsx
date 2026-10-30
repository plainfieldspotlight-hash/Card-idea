import { Suspense } from "react";
import Link from "next/link";
import { connection } from "next/server";
import { prisma } from "@/lib/db";
import { REVIEW_INTERVALS_DAYS } from "@/lib/review";
import { PageHeader } from "@/components/page-header";
import { ReviewCard } from "@/components/review-card";
import { Notice } from "@/components/ui";
import { InstallBanner } from "@/components/pwa";

export default function TodayPage(props: PageProps<"/">) {
  return (
    <>
      <PageHeader title="Today" subtitle="Ideas due for review, one at a time." />
      <InstallBanner />
      <Suspense fallback={<DueSkeleton />}>
        <Review searchParams={props.searchParams} />
      </Suspense>
    </>
  );
}

async function Review({ searchParams }: { searchParams: PageProps<"/">["searchParams"] }) {
  await connection(); // "today" is request time, never build time
  const query = await searchParams;
  const error = typeof query.error === "string" ? query.error : null;

  const [due, stats] = await Promise.all([
    prisma.idea.findMany({
      where: { status: "active", nextReviewAt: { lte: new Date() } },
      orderBy: [{ nextReviewAt: "asc" }, { createdAt: "asc" }],
      include: {
        source: { select: { title: true, type: true } },
        goal: { select: { name: true } },
        area: { select: { name: true } },
        tags: { include: { tag: { select: { name: true } } } },
      },
    }),
    prisma.idea.aggregate({ where: { status: "active" }, _count: true, _sum: { appliedCount: true } }),
  ]);

  if (due.length === 0) {
    return (
      <>
        <div className="rounded-3xl border border-border bg-card p-6 text-center">
          <p className="text-lg font-medium">Nothing due.</p>
          <p className="mt-1 text-sm text-muted">
            <Link href="/add" className="text-accent underline-offset-2 hover:underline">
              Add an idea
            </Link>{" "}
            or import a source.
          </p>
        </div>
        <Stats active={stats._count} applied={stats._sum.appliedCount ?? 0} />
      </>
    );
  }

  const idea = due[0];
  const nextIndex = Math.min(idea.reviewIntervalIndex + 1, REVIEW_INTERVALS_DAYS.length - 1);

  return (
    <>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <ReviewCard
        key={idea.id}
        idea={idea}
        position={1}
        total={due.length}
        nextIntervalDays={REVIEW_INTERVALS_DAYS[nextIndex]}
      />
      <Stats active={stats._count} applied={stats._sum.appliedCount ?? 0} />
    </>
  );
}

function Stats({ active, applied }: { active: number; applied: number }) {
  return (
    <dl className="mt-8 grid grid-cols-2 gap-3 text-center text-sm">
      <div className="rounded-2xl border border-border bg-card p-3">
        <dt className="text-xs uppercase tracking-wide text-muted">Ideas applied</dt>
        <dd className="text-2xl font-semibold tabular-nums">{applied}</dd>
      </div>
      <div className="rounded-2xl border border-border bg-card p-3">
        <dt className="text-xs uppercase tracking-wide text-muted">Active ideas</dt>
        <dd className="text-2xl font-semibold tabular-nums">{active}</dd>
      </div>
    </dl>
  );
}

function DueSkeleton() {
  return <div className="h-56 animate-pulse rounded-3xl border border-border bg-card" />;
}
