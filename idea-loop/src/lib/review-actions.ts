"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { prisma } from "@/lib/db";
import { REVIEW_INTERVALS_DAYS, nextReviewDate } from "@/lib/review";

// The review rule, exactly as written in SPEC.md:
//   Used it  -> review_interval_index + 1, next_review_at = today + that interval,
//               one applications row, applied_count + 1
//   Not yet  -> keep the index, next_review_at = today + current interval
//   Archive  -> status = archived, next_review_at = null

const MAX_INDEX = REVIEW_INTERVALS_DAYS.length - 1;

function id(formData: FormData): string {
  const value = formData.get("id");
  return typeof value === "string" ? value : "";
}

function done(): never {
  revalidatePath("/", "layout");
  redirect("/");
}

export async function markUsed(formData: FormData) {
  const ideaId = id(formData);
  const noteRaw = formData.get("note");
  const note = typeof noteRaw === "string" ? noteRaw.trim() : "";
  if (!ideaId) return;
  if (!note) redirect(`/?error=${encodeURIComponent("Add one line about where you used it.")}#review`);

  const idea = await prisma.idea.findUnique({ where: { id: ideaId }, select: { reviewIntervalIndex: true } });
  if (!idea) done();

  const nextIndex = Math.min(idea.reviewIntervalIndex + 1, MAX_INDEX);
  await prisma.$transaction([
    prisma.application.create({ data: { ideaId, note } }),
    prisma.idea.update({
      where: { id: ideaId },
      data: {
        reviewIntervalIndex: nextIndex,
        nextReviewAt: nextReviewDate(nextIndex),
        appliedCount: { increment: 1 },
      },
    }),
  ]);
  done();
}

export async function markNotYet(formData: FormData) {
  const ideaId = id(formData);
  if (!ideaId) return;
  const idea = await prisma.idea.findUnique({ where: { id: ideaId }, select: { reviewIntervalIndex: true } });
  if (!idea) done();
  await prisma.idea.update({
    where: { id: ideaId },
    data: { nextReviewAt: nextReviewDate(idea.reviewIntervalIndex) },
  });
  done();
}

export async function archiveFromReview(formData: FormData) {
  const ideaId = id(formData);
  if (!ideaId) return;
  await prisma.idea.update({ where: { id: ideaId }, data: { status: "archived", nextReviewAt: null } });
  done();
}

/** Dev tool from SPEC.md Phase 3: make an idea due right now so the loop can be tested without waiting. */
export async function makeDueNow(formData: FormData) {
  if (!devToolsEnabled()) return;
  const ideaId = id(formData);
  if (!ideaId) return;
  await prisma.idea.update({
    where: { id: ideaId },
    data: { status: "active", nextReviewAt: new Date(Date.now() - 1000) },
  });
  revalidatePath("/", "layout");
  redirect("/");
}

export async function devToolsEnabled(): Promise<boolean> {
  return process.env.NODE_ENV !== "production" || process.env.IDEA_LOOP_DEV_TOOLS === "1";
}
