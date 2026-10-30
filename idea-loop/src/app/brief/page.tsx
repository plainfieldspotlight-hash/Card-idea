import { PageHeader } from "@/components/page-header";
import { Placeholder } from "@/components/placeholder";

export default function BriefPage() {
  return (
    <>
      <PageHeader title="Brief" subtitle="Turn a goal or tag into a one-page document." />
      <Placeholder phase={5}>
        Pick a goal or tag and a format (talking points, post draft, meeting prep). Copy or
        download the result as markdown.
      </Placeholder>
    </>
  );
}
