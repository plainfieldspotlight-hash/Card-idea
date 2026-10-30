import { Suspense } from "react";
import { connection } from "next/server";
import { PageHeader } from "@/components/page-header";
import { IdeaForm } from "@/components/idea-form";
import { Notice } from "@/components/ui";
import { createIdea } from "@/lib/actions";
import { formOptions } from "@/lib/queries";

export default function AddPage(props: PageProps<"/add">) {
  return (
    <>
      <PageHeader title="Add" subtitle="Capture an idea in under ten seconds." />
      <Suspense fallback={<FormSkeleton />}>
        <AddForm searchParams={props.searchParams} />
      </Suspense>
    </>
  );
}

async function AddForm({ searchParams }: { searchParams: PageProps<"/add">["searchParams"] }) {
  await connection();
  const params = await searchParams;
  const options = await formOptions();
  const saved = params.saved === "1";
  const error = typeof params.error === "string" ? params.error : null;

  return (
    <>
      {saved ? <Notice tone="success">Saved. It comes back for review tomorrow.</Notice> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
      <IdeaForm action={createIdea} {...options} submitLabel="Save idea" />
      <p className="mt-6 text-center text-xs text-muted">
        Import from a URL or file arrives in Phase 4.
      </p>
    </>
  );
}

function FormSkeleton() {
  return (
    <div className="space-y-5">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="h-12 animate-pulse rounded-xl border border-border bg-card" />
      ))}
    </div>
  );
}
