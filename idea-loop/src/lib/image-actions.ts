"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { prisma } from "@/lib/db";

const MAX_BYTES = 3 * 1024 * 1024; // 3 MB is plenty for a cover

import type { ImageKind } from "@/lib/cover";

type Kind = ImageKind;

function back(kind: Kind, id: string, error?: string) {
  const base = kind === "goal" ? `/goals/${id}/edit` : kind === "area" ? `/areas/${id}` : `/topics/${id}`;
  redirect(error ? `${base}?error=${encodeURIComponent(error)}` : base);
}

function readKind(formData: FormData): Kind {
  const raw = formData.get("kind");
  return raw === "tag" || raw === "area" ? raw : "goal";
}

async function write(kind: Kind, id: string, data: { imageUrl: string | null; imageData: Uint8Array<ArrayBuffer> | null; imageMime: string | null }) {
  if (kind === "goal") await prisma.goal.update({ where: { id }, data });
  else if (kind === "area") await prisma.area.update({ where: { id }, data });
  else await prisma.tag.update({ where: { id }, data });
  revalidatePath("/", "layout");
}

/** Set a goal's or tag's image from an uploaded file or a pasted URL. */
export async function setImage(formData: FormData) {
  const kind = readKind(formData);
  const id = String(formData.get("id") ?? "");
  if (!id) redirect("/");

  const file = formData.get("file");
  const url = String(formData.get("url") ?? "").trim();

  if (file instanceof File && file.size > 0) {
    if (!file.type.startsWith("image/")) back(kind, id, "That file is not an image.");
    if (file.size > MAX_BYTES) back(kind, id, "Keep images under 3 MB.");
    const bytes = new Uint8Array(await file.arrayBuffer());
    await write(kind, id, { imageUrl: null, imageData: bytes, imageMime: file.type });
    back(kind, id);
  }

  if (url) {
    if (!/^https?:\/\//i.test(url)) back(kind, id, "Paste a full http(s) image link.");
    await write(kind, id, { imageUrl: url, imageData: null, imageMime: null });
    back(kind, id);
  }

  back(kind, id, "Choose a file or paste a link first.");
}

/** Remove the custom image and fall back to the generated cover. */
export async function clearImage(formData: FormData) {
  const kind = readKind(formData);
  const id = String(formData.get("id") ?? "");
  if (!id) redirect("/");
  await write(kind, id, { imageUrl: null, imageData: null, imageMime: null });
  back(kind, id);
}
