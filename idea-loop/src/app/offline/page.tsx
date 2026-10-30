import Link from "next/link";
import { PageHeader } from "@/components/page-header";

// Shown by the service worker when a page cannot be fetched.
export default function OfflinePage() {
  return (
    <>
      <PageHeader title="You're offline" subtitle="Idea Loop needs a connection to load and save ideas." />
      <div className="rounded-3xl border border-border bg-card p-6 text-center text-sm text-muted">
        <p>Reconnect and try again.</p>
        <Link href="/" className="mt-3 inline-block text-accent underline-offset-2 hover:underline">
          Back to Today
        </Link>
      </div>
    </>
  );
}
