import { Cover } from "@/components/cover";
import { Button, Card, Input } from "@/components/ui";
import { SubmitButton } from "@/components/submit-button";
import { clearImage, setImage } from "@/lib/image-actions";

export function ImageForm({
  kind,
  id,
  name,
  src,
}: {
  kind: "goal" | "tag";
  id: string;
  name: string;
  src: string | null;
}) {
  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold">Image</h2>
      <Cover name={name} src={src} size="lg" className="mb-4 aspect-[2/1] w-full rounded-xl" />
      <form action={setImage} className="space-y-3">
        <input type="hidden" name="kind" value={kind} />
        <input type="hidden" name="id" value={id} />
        <label className="block text-sm font-medium">
          Upload a picture
          <input
            type="file"
            name="file"
            accept="image/*"
            className="mt-1.5 block w-full text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-accent file:px-3 file:py-2 file:text-sm file:font-medium file:text-accent-foreground"
          />
        </label>
        <div className="flex items-center gap-2 text-xs text-muted">
          <span className="h-px flex-1 bg-border" />
          or
          <span className="h-px flex-1 bg-border" />
        </div>
        <label className="block text-sm font-medium">
          Paste an image link
          <Input name="url" type="url" placeholder="https://…" className="mt-1.5" />
        </label>
        <SubmitButton className="w-full" variant="secondary" pendingLabel="Uploading…">
          Set image
        </SubmitButton>
      </form>
      {src ? (
        <form action={clearImage} className="mt-3">
          <input type="hidden" name="kind" value={kind} />
          <input type="hidden" name="id" value={id} />
          <Button type="submit" variant="ghost" className="w-full">
            Remove and use the generated cover
          </Button>
        </form>
      ) : (
        <p className="mt-3 text-center text-xs text-muted">
          Without a picture, {kind === "goal" ? "the goal" : "the topic"} gets this generated cover.
        </p>
      )}
    </Card>
  );
}
