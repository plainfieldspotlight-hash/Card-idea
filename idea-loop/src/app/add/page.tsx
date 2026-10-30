import { PageHeader } from "@/components/page-header";
import { Placeholder } from "@/components/placeholder";

export default function AddPage() {
  return (
    <>
      <PageHeader title="Add" subtitle="Capture an idea in under ten seconds." />
      <Placeholder phase={2}>
        Four-field form: the idea, its source, a tag, and where you could use it. An Import tab
        follows in Phase 4.
      </Placeholder>
    </>
  );
}
