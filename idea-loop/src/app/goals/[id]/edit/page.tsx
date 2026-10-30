import { Suspense } from "react";
import { connection } from "next/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import { prisma } from "@/lib/db";
import { deleteGoal, updateGoal } from "@/lib/actions";
import { PageHeader } from "@/components/page-header";
import { Button, Field, Input, Notice, Select } from "@/components/ui";
import { SubmitButton } from "@/components/submit-button";

export default function EditGoalPage(props: PageProps<"/goals/[id]/edit">) {
  return (
    <Suspense fallback={<div className="h-48 animate-pulse rounded-2xl border border-border bg-card" />}>
      <EditGoal params={props.params} searchParams={props.searchParams} />
    </Suspense>
  );
}

async function EditGoal({
  params,
  searchParams,
}: {
  params: PageProps<"/goals/[id]/edit">["params"];
  searchParams: PageProps<"/goals/[id]/edit">["searchParams"];
}) {
  await connection();
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const goal = await prisma.goal.findUnique({
    where: { id },
    include: { _count: { select: { ideas: true } } },
  });
  if (!goal) notFound();
  const error = typeof query.error === "string" ? query.error : null;

  return (
    <>
      <Link href="/goals" className="mb-4 inline-block text-sm text-muted hover:text-foreground">
        ← Goals
      </Link>
      <PageHeader title="Edit goal" />
      {error ? <Notice tone="error">{error}</Notice> : null}

      <form action={updateGoal} className="space-y-4">
        <input type="hidden" name="id" value={goal.id} />
        <Field label="Name" htmlFor="name">
          <Input id="name" name="name" required defaultValue={goal.name} />
        </Field>
        <Field label="Description" hint="optional" htmlFor="description">
          <Input id="description" name="description" defaultValue={goal.description ?? ""} />
        </Field>
        <Field label="Status" htmlFor="status">
          <Select id="status" name="status" defaultValue={goal.status}>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
            <option value="done">Done</option>
          </Select>
        </Field>
        <SubmitButton className="w-full">Save goal</SubmitButton>
      </form>

      <form action={deleteGoal} className="mt-8 border-t border-border pt-6">
        <input type="hidden" name="id" value={goal.id} />
        <p className="mb-3 text-xs text-muted">
          Deleting keeps the {goal._count.ideas} linked {goal._count.ideas === 1 ? "idea" : "ideas"} and unlinks
          them from this goal.
        </p>
        <Button type="submit" variant="danger">
          Delete goal
        </Button>
      </form>
    </>
  );
}
