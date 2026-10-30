"use client";

import { useFormStatus } from "react-dom";
import { Button } from "@/components/ui";
import type { ComponentProps } from "react";

export function SubmitButton({
  children,
  pendingLabel = "Saving…",
  ...props
}: ComponentProps<typeof Button> & { pendingLabel?: string }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending} aria-busy={pending} {...props}>
      {pending ? pendingLabel : children}
    </Button>
  );
}
