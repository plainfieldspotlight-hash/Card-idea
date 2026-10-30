import Link from "next/link";
import { Chip } from "@/components/ui";

export type IdeaCardData = {
  id: string;
  text: string;
  status: string;
  appliedCount: number;
  source: { title: string } | null;
  tags: { tag: { name: string } }[];
};

export function IdeaCard({ idea }: { idea: IdeaCardData }) {
  return (
    <li>
      <Link
        href={`/ideas/${idea.id}`}
        className={`block rounded-2xl border border-border bg-card p-4 transition-colors hover:border-accent/60 ${
          idea.status === "archived" ? "opacity-60" : ""
        }`}
      >
        <p className="text-sm leading-relaxed">{idea.text}</p>
        <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-muted">
          {idea.source ? <span className="mr-1">{idea.source.title}</span> : null}
          {idea.tags.map(({ tag }) => (
            <Chip key={tag.name}>#{tag.name}</Chip>
          ))}
          {idea.appliedCount > 0 ? <Chip active>applied ×{idea.appliedCount}</Chip> : null}
          {idea.status === "archived" ? <Chip>archived</Chip> : null}
        </div>
      </Link>
    </li>
  );
}
