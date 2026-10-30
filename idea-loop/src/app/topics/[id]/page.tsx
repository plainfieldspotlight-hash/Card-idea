import { Suspense } from "react";
import { connection } from "next/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import { prisma } from "@/lib/db";
import { renameTag } from "@/lib/actions";
import { imageSrc } from "@/lib/cover";
import { PageHeader } from "@/components/page-header";
import { IdeaCard } from "@/components/idea-card";
import { ImageForm } from "@/components/image-form";
import { Card, Field, Input, Notice } from "@/components/ui";
import { SubmitButton } from "@/components/submit-button";

export default function TopicPage(props: PageProps<"/topics/[id]">) {
  return (
    <Suspense fallback={<div className="h-64 animate-pulse rounded-2xl border border-border bg-card" />}>
      <Topic params={props.params} searchParams={props.searchParams} />
    </Suspense>
  );
}

async function Topic({
  params,
  searchParams,
}: {
  params: PageProps<"/topics/[id]">["params"];
  searchParams: PageProps<"/topics/[id]">["searchParams"];
}) {
  await connection();
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const tag = await prisma.tag.findUnique({
    where: { id },
    include: {
      ideas: {
        orderBy: { createdAt: "desc" },
        include: {
          idea: {
            include: { source: { select: { title: true } }, tags: { include: { tag: { select: { name: true } } } } },
          },
        },
      },
    },
  });
  if (!tag) notFound();
  const error = typeof query.error === "string" ? query.error : null;
  const ideas = tag.ideas.map((link) => link.idea);

  return (
    <>
      <Link href="/topics" className="mb-4 inline-block text-sm text-muted hover:text-foreground">
        ← Topics
      </Link>
      <PageHeader title={`#${tag.name}`} subtitle={`${ideas.length} ${ideas.length === 1 ? "idea" : "ideas"}`} />
      {error ? <Notice tone="error">{error}</Notice> : null}

      <div className="space-y-6">
        <ImageForm kind="tag" id={tag.id} name={tag.name} src={imageSrc("tag", tag)} />

        <Card>
          <h2 className="mb-3 text-sm font-semibold">Rename</h2>
          <form action={renameTag} className="flex gap-2">
            <input type="hidden" name="id" value={tag.id} />
            <Field label="Name" htmlFor="tag-name">
              <Input id="tag-name" name="name" required defaultValue={tag.name} />
            </Field>
            <SubmitButton variant="secondary" className="self-end">
              Save
            </SubmitButton>
          </form>
        </Card>

        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">Ideas</h2>
          {ideas.length === 0 ? (
            <p className="text-sm text-muted">No ideas carry this tag yet.</p>
          ) : (
            <ul className="space-y-2">
              {ideas.map((idea) => (
                <IdeaCard key={idea.id} idea={idea} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
