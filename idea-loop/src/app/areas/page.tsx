import { Suspense } from "react";
import { connection } from "next/server";
import Link from "next/link";
import { prisma } from "@/lib/db";
import { createArea } from "@/lib/actions";
import { imageSrc } from "@/lib/cover";
import { PageHeader } from "@/components/page-header";
import { Cover } from "@/components/cover";
import { Card, Field, Input, Notice } from "@/components/ui";
import { SubmitButton } from "@/components/submit-button";

export default function AreasPage(props: PageProps<"/areas">) {
  return (
    <>
      <Link href="/goals" className="mb-4 inline-block text-sm text-muted hover:text-foreground">
        ← Goals
      </Link>
      <PageHeader title="Areas" subtitle="Career, family, friends: the routes your ideas run on." />
      <Suspense fallback={<div className="h-40 animate-pulse rounded-2xl border border-border bg-card" />}>
        <AreaGrid searchParams={props.searchParams} />
      </Suspense>
    </>
  );
}

async function AreaGrid({ searchParams }: { searchParams: PageProps<"/areas">["searchParams"] }) {
  await connection();
  const query = await searchParams;
  const error = typeof query.error === "string" ? query.error : null;

  const areas = await prisma.area.findMany({
    orderBy: [{ sortOrder: "asc" }, { name: "asc" }],
    include: {
      _count: { select: { goals: true } },
      ideas: { where: { status: "active" }, select: { appliedCount: true } },
    },
  });

  return (
    <>
      {error ? <Notice tone="error">{error}</Notice> : null}

      <ul className="mb-8 grid grid-cols-2 gap-3">
        {areas.map((area) => {
          const applied = area.ideas.filter((i) => i.appliedCount > 0).length;
          return (
            <li key={area.id}>
              <Link
                href={`/areas/${area.id}`}
                className="block overflow-hidden rounded-2xl border border-border bg-card transition-colors hover:border-accent/60"
              >
                <Cover name={area.name} src={imageSrc("area", area)} className="aspect-[4/3] w-full" />
                <div className="p-3">
                  <p className="truncate text-sm font-medium">{area.name}</p>
                  <p className="text-xs text-muted tabular-nums">
                    {area._count.goals} {area._count.goals === 1 ? "goal" : "goals"} · {area.ideas.length}{" "}
                    {area.ideas.length === 1 ? "idea" : "ideas"}
                    {applied ? ` · ${applied} applied` : ""}
                  </p>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>

      <Card>
        <h2 className="mb-3 text-sm font-semibold">New area</h2>
        <form action={createArea} className="space-y-3">
          <Field label="Name" htmlFor="area-name">
            <Input id="area-name" name="name" required placeholder="Community" />
          </Field>
          <Field label="Description" hint="optional" htmlFor="area-description">
            <Input id="area-description" name="description" placeholder="What this part of life is about" />
          </Field>
          <SubmitButton className="w-full">Add area</SubmitButton>
        </form>
      </Card>
    </>
  );
}
