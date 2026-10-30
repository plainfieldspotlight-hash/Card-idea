import { Suspense } from "react";
import { connection } from "next/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import { prisma } from "@/lib/db";
import { archiveIdea, deleteIdea, restoreIdea } from "@/lib/actions";
import { devToolsEnabled, makeDueNow } from "@/lib/review-actions";
import { REVIEW_INTERVALS_DAYS } from "@/lib/review";
import { Button, Card, Chip, LinkButton, formatDate } from "@/components/ui";

export default function IdeaDetailPage(props: PageProps<"/ideas/[id]">) {
  return (
    <Suspense fallback={<div className="h-40 animate-pulse rounded-2xl border border-border bg-card" />}>
      <IdeaDetail params={props.params} />
    </Suspense>
  );
}

async function IdeaDetail({ params }: { params: PageProps<"/ideas/[id]">["params"] }) {
  await connection();
  const { id } = await params;
  const idea = await prisma.idea.findUnique({
    where: { id },
    include: {
      source: true,
      goal: true,
      area: true,
      tags: { include: { tag: true } },
      applications: { orderBy: { appliedAt: "desc" } },
    },
  });
  if (!idea) notFound();
  const devTools = await devToolsEnabled();

  const archived = idea.status === "archived";
  const intervalDays = REVIEW_INTERVALS_DAYS[Math.min(idea.reviewIntervalIndex, REVIEW_INTERVALS_DAYS.length - 1)];

  return (
    <article className="space-y-5">
      <Link href="/library" className="text-sm text-muted hover:text-foreground">
        ← Library
      </Link>

      <Card>
        <p className="text-lg leading-relaxed">{idea.text}</p>
        <dl className="mt-4 space-y-1.5 text-sm text-muted">
          {idea.source ? (
            <div>
              <dt className="inline">Source: </dt>
              <dd className="inline text-foreground">
                {idea.source.title}
                {idea.source.author ? `, ${idea.source.author}` : ""}
                <span className="text-muted"> · {idea.source.type}</span>
              </dd>
            </div>
          ) : null}
          <div>
            <dt className="inline">Area: </dt>
            <dd className="inline text-foreground">
              {idea.area ? (
                <Link href={`/areas/${idea.area.id}`} className="hover:underline">
                  {idea.area.name}
                </Link>
              ) : (
                "None"
              )}
            </dd>
          </div>
          <div>
            <dt className="inline">Goal: </dt>
            <dd className="inline text-foreground">{idea.goal?.name ?? "None"}</dd>
          </div>
          {idea.useNote ? (
            <div>
              <dt className="inline">Where I could use this: </dt>
              <dd className="inline text-foreground">{idea.useNote}</dd>
            </div>
          ) : null}
        </dl>
        {idea.tags.length ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {idea.tags.map(({ tag }) => (
              <Chip key={tag.id}>#{tag.name}</Chip>
            ))}
          </div>
        ) : null}
      </Card>

      {idea.context || idea.counterpoint ? (
        <Card className="space-y-4">
          {idea.context ? (
            <section>
              <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Context</h2>
              <p className="text-sm leading-relaxed">{idea.context}</p>
            </section>
          ) : null}
          {idea.counterpoint ? (
            <section>
              <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Counterpoint</h2>
              <p className="text-sm leading-relaxed">{idea.counterpoint}</p>
            </section>
          ) : null}
        </Card>
      ) : null}

      <Card>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted">Applied</p>
            <p className="text-2xl font-semibold tabular-nums">{idea.appliedCount}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted">Next review</p>
            <p className="font-medium">{archived ? "Archived" : formatDate(idea.nextReviewAt)}</p>
            {!archived ? <p className="text-xs text-muted">every {intervalDays} {intervalDays === 1 ? "day" : "days"}</p> : null}
          </div>
        </div>
        {idea.applications.length ? (
          <ul className="mt-4 space-y-2 border-t border-border pt-4">
            {idea.applications.map((a) => (
              <li key={a.id} className="text-sm">
                <span className="text-muted">{formatDate(a.appliedAt)} · </span>
                {a.note}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-4 border-t border-border pt-4 text-sm text-muted">
            Not used yet. The Today screen asks when it comes due.
          </p>
        )}
      </Card>

      <div className="flex flex-wrap gap-2">
        <LinkButton href={`/ideas/${idea.id}/edit`} variant="secondary">
          Edit
        </LinkButton>
        {archived ? (
          <form action={restoreIdea}>
            <input type="hidden" name="id" value={idea.id} />
            <Button type="submit" variant="secondary">
              Restore
            </Button>
          </form>
        ) : (
          <form action={archiveIdea}>
            <input type="hidden" name="id" value={idea.id} />
            <Button type="submit" variant="secondary">
              Archive
            </Button>
          </form>
        )}
        <form action={deleteIdea} className="ml-auto">
          <input type="hidden" name="id" value={idea.id} />
          <Button type="submit" variant="danger">
            Delete
          </Button>
        </form>
      </div>
      <p className="text-xs text-muted">Created {formatDate(idea.createdAt)}</p>

      {devTools ? (
        <form action={makeDueNow} className="rounded-2xl border border-dashed border-border p-4">
          <input type="hidden" name="id" value={idea.id} />
          <p className="mb-2 text-xs text-muted">
            Dev only: set next review to now so this idea shows up on Today without waiting.
          </p>
          <Button type="submit" variant="secondary">
            Make due now
          </Button>
        </form>
      ) : null}
    </article>
  );
}
