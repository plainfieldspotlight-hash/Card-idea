import { Suspense } from "react";
import { connection } from "next/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import { prisma } from "@/lib/db";
import { deleteArea, updateArea } from "@/lib/actions";
import { imageSrc } from "@/lib/cover";
import { PageHeader } from "@/components/page-header";
import { Cover } from "@/components/cover";
import { IdeaCard } from "@/components/idea-card";
import { ImageForm } from "@/components/image-form";
import { Button, Card, Field, Input, Notice } from "@/components/ui";
import { SubmitButton } from "@/components/submit-button";

export default function AreaPage(props: PageProps<"/areas/[id]">) {
  return (
    <Suspense fallback={<div className="h-64 animate-pulse rounded-2xl border border-border bg-card" />}>
      <Area params={props.params} searchParams={props.searchParams} />
    </Suspense>
  );
}

async function Area({
  params,
  searchParams,
}: {
  params: PageProps<"/areas/[id]">["params"];
  searchParams: PageProps<"/areas/[id]">["searchParams"];
}) {
  await connection();
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const area = await prisma.area.findUnique({
    where: { id },
    include: {
      goals: {
        orderBy: [{ status: "asc" }, { createdAt: "asc" }],
        include: { ideas: { where: { status: "active" }, select: { appliedCount: true } } },
      },
      ideas: {
        where: { status: "active", goalId: null },
        orderBy: { createdAt: "desc" },
        include: { source: { select: { title: true } }, tags: { include: { tag: { select: { name: true } } } } },
      },
    },
  });
  if (!area) notFound();
  const error = typeof query.error === "string" ? query.error : null;
  const totalIdeas = area.goals.reduce((n, g) => n + g.ideas.length, 0) + area.ideas.length;

  return (
    <>
      <Link href="/areas" className="mb-4 inline-block text-sm text-muted hover:text-foreground">
        ← Areas
      </Link>
      <PageHeader
        title={area.name}
        subtitle={`${area.goals.length} ${area.goals.length === 1 ? "goal" : "goals"} · ${totalIdeas} ${
          totalIdeas === 1 ? "idea" : "ideas"
        }`}
      />
      {error ? <Notice tone="error">{error}</Notice> : null}

      <div className="space-y-6">
        <section>
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Goals</h2>
            <Link href="/goals" className="text-xs text-muted hover:text-foreground">
              Add a goal
            </Link>
          </div>
          {area.goals.length === 0 ? (
            <p className="text-sm text-muted">No goals in this area yet.</p>
          ) : (
            <ul className="space-y-2">
              {area.goals.map((goal) => {
                const applied = goal.ideas.filter((i) => i.appliedCount > 0).length;
                return (
                  <li key={goal.id}>
                    <Link
                      href={`/goals/${goal.id}/edit`}
                      className={`flex items-center gap-3 rounded-2xl border border-border bg-card p-3 transition-colors hover:border-accent/60 ${
                        goal.status !== "active" ? "opacity-60" : ""
                      }`}
                    >
                      <Cover name={goal.name} src={imageSrc("goal", goal)} size="sm" className="h-12 w-12 shrink-0 rounded-xl" />
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{goal.name}</p>
                        <p className="text-xs text-muted tabular-nums">
                          {goal.ideas.length} {goal.ideas.length === 1 ? "idea" : "ideas"} · {applied} applied
                        </p>
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {area.ideas.length ? (
          <section>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">Ideas without a goal</h2>
            <ul className="space-y-2">
              {area.ideas.map((idea) => (
                <IdeaCard key={idea.id} idea={idea} />
              ))}
            </ul>
          </section>
        ) : null}

        <ImageForm kind="area" id={area.id} name={area.name} src={imageSrc("area", area)} />

        <Card>
          <h2 className="mb-3 text-sm font-semibold">Edit</h2>
          <form action={updateArea} className="space-y-3">
            <input type="hidden" name="id" value={area.id} />
            <Field label="Name" htmlFor="name">
              <Input id="name" name="name" required defaultValue={area.name} />
            </Field>
            <Field label="Description" hint="optional" htmlFor="description">
              <Input id="description" name="description" defaultValue={area.description ?? ""} />
            </Field>
            <SubmitButton className="w-full" variant="secondary">
              Save area
            </SubmitButton>
          </form>
        </Card>

        <form action={deleteArea} className="border-t border-border pt-6">
          <input type="hidden" name="id" value={area.id} />
          <p className="mb-3 text-xs text-muted">
            Deleting keeps its goals and ideas and leaves them without an area.
          </p>
          <Button type="submit" variant="danger">
            Delete area
          </Button>
        </form>
      </div>
    </>
  );
}
