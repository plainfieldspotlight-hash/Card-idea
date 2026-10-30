"use client";

import { useState } from "react";
import Link from "next/link";
import { archiveFromReview, markNotYet, markUsed } from "@/lib/review-actions";
import { Button, Chip, Input } from "@/components/ui";
import { SubmitButton } from "@/components/submit-button";

export type ReviewIdea = {
  id: string;
  text: string;
  context: string | null;
  counterpoint: string | null;
  useNote: string | null;
  appliedCount: number;
  reviewIntervalIndex: number;
  source: { title: string; type: string } | null;
  goal: { name: string } | null;
  area: { name: string } | null;
  tags: { tag: { name: string } }[];
};

export function ReviewCard({
  idea,
  position,
  total,
  nextIntervalDays,
}: {
  idea: ReviewIdea;
  position: number;
  total: number;
  nextIntervalDays: number;
}) {
  const [noting, setNoting] = useState(false);

  return (
    <section id="review" aria-labelledby="review-heading" className="space-y-4">
      <div className="flex items-center justify-between text-xs text-muted">
        <span id="review-heading" className="tabular-nums">
          {position} of {total} due
        </span>
        <span>
          {idea.area?.name ?? "No area"}
          {idea.goal ? ` · ${idea.goal.name}` : ""}
        </span>
      </div>

      <article className="rounded-3xl border border-border bg-card p-5 shadow-sm">
        <p className="text-xl leading-relaxed">{idea.text}</p>

        <div className="mt-4 flex flex-wrap items-center gap-1.5 text-xs text-muted">
          {idea.source ? <span className="mr-1">{idea.source.title}</span> : null}
          {idea.tags.map(({ tag }) => (
            <Chip key={tag.name}>#{tag.name}</Chip>
          ))}
          {idea.appliedCount > 0 ? <Chip active>applied ×{idea.appliedCount}</Chip> : null}
        </div>

        {idea.useNote ? (
          <p className="mt-4 rounded-xl bg-background px-3 py-2 text-sm">
            <span className="text-muted">Where you said you could use it: </span>
            {idea.useNote}
          </p>
        ) : null}

        {idea.context || idea.counterpoint ? (
          <details className="group mt-4">
            <summary className="cursor-pointer select-none text-sm font-medium text-accent">
              <span className="group-open:hidden">Show more</span>
              <span className="hidden group-open:inline">Show less</span>
            </summary>
            <div className="mt-3 space-y-3 text-sm leading-relaxed">
              {idea.context ? (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Context</p>
                  <p>{idea.context}</p>
                </div>
              ) : null}
              {idea.counterpoint ? (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Counterpoint</p>
                  <p>{idea.counterpoint}</p>
                </div>
              ) : null}
            </div>
          </details>
        ) : null}
      </article>

      {noting ? (
        <form action={markUsed} className="space-y-3 rounded-2xl border border-accent/40 bg-card p-4">
          <input type="hidden" name="id" value={idea.id} />
          <label htmlFor="note" className="block text-sm font-medium">
            Where did you use it?
          </label>
          <Input id="note" name="note" required autoFocus placeholder="In the Thursday forecast review…" />
          <p className="text-xs text-muted">
            Next review in {nextIntervalDays} {nextIntervalDays === 1 ? "day" : "days"}.
          </p>
          <div className="flex gap-2">
            <SubmitButton className="min-h-12 flex-1" pendingLabel="Saving…">
              Save
            </SubmitButton>
            <Button type="button" variant="secondary" className="min-h-12" onClick={() => setNoting(false)}>
              Back
            </Button>
          </div>
        </form>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          <Button type="button" className="min-h-14 text-base" onClick={() => setNoting(true)}>
            Used it
          </Button>
          <form action={markNotYet} className="contents">
            <input type="hidden" name="id" value={idea.id} />
            <SubmitButton variant="secondary" className="min-h-14 text-base" pendingLabel="Saving…">
              Not yet
            </SubmitButton>
          </form>
        </div>
      )}

      <div className="flex items-center justify-between px-1 text-xs text-muted">
        <Link href={`/ideas/${idea.id}`} className="hover:text-foreground">
          Open details
        </Link>
        <form action={archiveFromReview}>
          <input type="hidden" name="id" value={idea.id} />
          <button type="submit" className="min-h-10 px-2 hover:text-foreground">
            Archive
          </button>
        </form>
      </div>
    </section>
  );
}
