import { Suspense } from "react";
import { connection } from "next/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import { prisma } from "@/lib/db";
import { updateIdea } from "@/lib/actions";
import { formOptions } from "@/lib/queries";
import { IdeaForm } from "@/components/idea-form";
import { PageHeader } from "@/components/page-header";
import { Notice } from "@/components/ui";

export default function EditIdeaPage(props: PageProps<"/ideas/[id]/edit">) {
  return (
    <Suspense fallback={<div className="h-64 animate-pulse rounded-2xl border border-border bg-card" />}>
      <EditIdea params={props.params} searchParams={props.searchParams} />
    </Suspense>
  );
}

async function EditIdea({
  params,
  searchParams,
}: {
  params: PageProps<"/ideas/[id]/edit">["params"];
  searchParams: PageProps<"/ideas/[id]/edit">["searchParams"];
}) {
  await connection();
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const [idea, options] = await Promise.all([
    prisma.idea.findUnique({
      where: { id },
      include: { source: true, tags: { include: { tag: true } } },
    }),
    formOptions(),
  ]);
  if (!idea) notFound();
  const error = typeof query.error === "string" ? query.error : null;

  return (
    <>
      <Link href={`/ideas/${id}`} className="mb-4 inline-block text-sm text-muted hover:text-foreground">
        ← Back
      </Link>
      <PageHeader title="Edit idea" />
      {error ? <Notice tone="error">{error}</Notice> : null}
      <IdeaForm
        action={updateIdea}
        {...options}
        showDepth
        submitLabel="Save changes"
        values={{
          id: idea.id,
          text: idea.text,
          sourceTitle: idea.source?.title ?? "",
          sourceType: idea.source?.type ?? "book",
          tags: idea.tags.map((t) => t.tag.name).join(", "),
          useNote: idea.useNote ?? "",
          goalId: idea.goalId,
          areaId: idea.areaId,
          context: idea.context,
          counterpoint: idea.counterpoint,
        }}
      />
    </>
  );
}
