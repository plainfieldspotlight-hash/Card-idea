import { Suspense } from "react";
import { connection } from "next/server";
import Link from "next/link";
import { prisma } from "@/lib/db";
import { PageHeader } from "@/components/page-header";
import { Cover } from "@/components/cover";
import { imageSrc } from "@/lib/cover";

export default function TopicsPage() {
  return (
    <>
      <Link href="/library" className="mb-4 inline-block text-sm text-muted hover:text-foreground">
        ← Library
      </Link>
      <PageHeader title="Topics" subtitle="Every tag, with its cover. Tap one to see its ideas or change the image." />
      <Suspense fallback={<div className="h-40 animate-pulse rounded-2xl border border-border bg-card" />}>
        <TopicGrid />
      </Suspense>
    </>
  );
}

async function TopicGrid() {
  await connection();
  const tags = await prisma.tag.findMany({
    orderBy: { name: "asc" },
    include: { _count: { select: { ideas: true } } },
  });

  if (tags.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-border bg-card p-5 text-center text-sm text-muted">
        No topics yet. Tags you add to ideas show up here.
      </p>
    );
  }

  return (
    <ul className="grid grid-cols-2 gap-3">
      {tags.map((tag) => (
        <li key={tag.id}>
          <Link
            href={`/topics/${tag.id}`}
            className="block overflow-hidden rounded-2xl border border-border bg-card transition-colors hover:border-accent/60"
          >
            <Cover name={tag.name} src={imageSrc("tag", tag)} className="aspect-[4/3] w-full" />
            <div className="p-3">
              <p className="truncate text-sm font-medium">#{tag.name}</p>
              <p className="text-xs text-muted tabular-nums">
                {tag._count.ideas} {tag._count.ideas === 1 ? "idea" : "ideas"}
              </p>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
