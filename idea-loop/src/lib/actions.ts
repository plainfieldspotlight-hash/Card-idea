"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { prisma } from "@/lib/db";
import { nextReviewDate } from "@/lib/review";

const SOURCE_TYPES = ["book", "article", "podcast", "person", "other"] as const;
const GOAL_STATUSES = ["active", "done", "paused"] as const;

function text(formData: FormData, key: string): string {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function optional(formData: FormData, key: string): string | null {
  const value = text(formData, key);
  return value.length ? value : null;
}

function parseTags(raw: string): string[] {
  return Array.from(
    new Set(
      raw
        .split(",")
        .map((t) => t.trim().toLowerCase().replace(/\s+/g, "-"))
        .filter(Boolean),
    ),
  );
}

/** Find or create a source by title. Returns null when no title was given. */
async function resolveSource(formData: FormData): Promise<string | null> {
  const title = text(formData, "sourceTitle");
  if (!title) return null;
  const rawType = text(formData, "sourceType");
  const type = (SOURCE_TYPES as readonly string[]).includes(rawType) ? rawType : "other";

  const existing = await prisma.source.findFirst({ where: { title } });
  if (existing) return existing.id;
  const created = await prisma.source.create({ data: { title, type } });
  return created.id;
}

async function resolveTags(formData: FormData): Promise<string[]> {
  const names = parseTags(text(formData, "tags"));
  const ids: string[] = [];
  for (const name of names) {
    const tag = await prisma.tag.upsert({ where: { name }, update: {}, create: { name } });
    ids.push(tag.id);
  }
  return ids;
}

function invalidateAll() {
  revalidatePath("/", "layout");
}

// ---------------------------------------------------------------------------
// Ideas
// ---------------------------------------------------------------------------

export async function createIdea(formData: FormData) {
  const ideaText = text(formData, "text");
  if (!ideaText) redirect("/add?error=Write+the+idea+first.");

  const sourceId = await resolveSource(formData);
  const tagIds = await resolveTags(formData);
  const goalId = optional(formData, "goalId");

  await prisma.idea.create({
    data: {
      text: ideaText,
      useNote: optional(formData, "useNote"),
      context: optional(formData, "context"),
      counterpoint: optional(formData, "counterpoint"),
      sourceId,
      goalId,
      reviewIntervalIndex: 0,
      nextReviewAt: nextReviewDate(0),
      tags: { create: tagIds.map((tagId) => ({ tagId })) },
    },
  });

  invalidateAll();
  redirect("/add?saved=1");
}

export async function updateIdea(formData: FormData) {
  const id = text(formData, "id");
  const ideaText = text(formData, "text");
  if (!id) redirect("/library");
  if (!ideaText) redirect(`/ideas/${id}/edit?error=Write+the+idea+first.`);

  const sourceId = await resolveSource(formData);
  const tagIds = await resolveTags(formData);
  const goalId = optional(formData, "goalId");

  await prisma.$transaction([
    prisma.ideaTag.deleteMany({ where: { ideaId: id } }),
    prisma.idea.update({
      where: { id },
      data: {
        text: ideaText,
        useNote: optional(formData, "useNote"),
        context: optional(formData, "context"),
        counterpoint: optional(formData, "counterpoint"),
        sourceId,
        goalId,
        tags: { create: tagIds.map((tagId) => ({ tagId })) },
      },
    }),
  ]);

  invalidateAll();
  redirect(`/ideas/${id}`);
}

export async function archiveIdea(formData: FormData) {
  const id = text(formData, "id");
  if (!id) return;
  // Review rule: archive sets status = archived and clears next_review_at.
  await prisma.idea.update({
    where: { id },
    data: { status: "archived", nextReviewAt: null },
  });
  invalidateAll();
  redirect(`/ideas/${id}`);
}

export async function restoreIdea(formData: FormData) {
  const id = text(formData, "id");
  if (!id) return;
  const idea = await prisma.idea.findUnique({ where: { id } });
  if (!idea) redirect("/library");
  // Coming back from the archive: resume at the current interval, due tomorrow at the earliest.
  await prisma.idea.update({
    where: { id },
    data: { status: "active", nextReviewAt: nextReviewDate(idea.reviewIntervalIndex) },
  });
  invalidateAll();
  redirect(`/ideas/${id}`);
}

export async function deleteIdea(formData: FormData) {
  const id = text(formData, "id");
  if (!id) return;
  await prisma.idea.delete({ where: { id } });
  invalidateAll();
  redirect("/library");
}

// ---------------------------------------------------------------------------
// Goals
// ---------------------------------------------------------------------------

export async function createGoal(formData: FormData) {
  const name = text(formData, "name");
  if (!name) redirect("/goals?error=Give+the+goal+a+name.");
  await prisma.goal.create({ data: { name, description: optional(formData, "description") } });
  invalidateAll();
  redirect("/goals");
}

export async function updateGoal(formData: FormData) {
  const id = text(formData, "id");
  const name = text(formData, "name");
  if (!id) redirect("/goals");
  if (!name) redirect(`/goals/${id}/edit?error=Give+the+goal+a+name.`);
  const rawStatus = text(formData, "status");
  const status = (GOAL_STATUSES as readonly string[]).includes(rawStatus) ? rawStatus : "active";
  await prisma.goal.update({
    where: { id },
    data: { name, description: optional(formData, "description"), status },
  });
  invalidateAll();
  redirect("/goals");
}

export async function deleteGoal(formData: FormData) {
  const id = text(formData, "id");
  if (!id) return;
  // Ideas keep existing; their goal_id becomes null (onDelete: SetNull).
  await prisma.goal.delete({ where: { id } });
  invalidateAll();
  redirect("/goals");
}

// ---------------------------------------------------------------------------
// Tags (topics)
// ---------------------------------------------------------------------------

export async function renameTag(formData: FormData) {
  const id = text(formData, "id");
  const [name] = parseTags(text(formData, "name"));
  if (!id) redirect("/topics");
  if (!name) redirect(`/topics/${id}?error=Give+the+topic+a+name.`);
  const clash = await prisma.tag.findUnique({ where: { name } });
  if (clash && clash.id !== id) redirect(`/topics/${id}?error=A+topic+with+that+name+already+exists.`);
  await prisma.tag.update({ where: { id }, data: { name } });
  invalidateAll();
  redirect(`/topics/${id}`);
}
