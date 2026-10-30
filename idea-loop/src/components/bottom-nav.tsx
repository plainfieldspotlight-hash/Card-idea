"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

type Item = { href: "/" | "/add" | "/library" | "/goals" | "/brief"; label: string; icon: ReactNode };

const items: Item[] = [
  { href: "/", label: "Today", icon: <TodayIcon /> },
  { href: "/add", label: "Add", icon: <AddIcon /> },
  { href: "/library", label: "Library", icon: <LibraryIcon /> },
  { href: "/goals", label: "Goals", icon: <GoalsIcon /> },
  { href: "/brief", label: "Brief", icon: <BriefIcon /> },
];

export function BottomNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-10 border-t border-border bg-card/95 backdrop-blur"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <ul className="mx-auto flex max-w-xl">
        {items.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`flex h-16 flex-col items-center justify-center gap-1 text-xs font-medium transition-colors ${
                  active ? "text-accent" : "text-muted hover:text-foreground"
                }`}
              >
                <span aria-hidden className="h-6 w-6">
                  {item.icon}
                </span>
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

const svgProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  className: "h-6 w-6",
};

function TodayIcon() {
  return (
    <svg {...svgProps}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
      <path d="m9 15 2 2 4-4" />
    </svg>
  );
}

function AddIcon() {
  return (
    <svg {...svgProps}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v8M8 12h8" />
    </svg>
  );
}

function LibraryIcon() {
  return (
    <svg {...svgProps}>
      <path d="M4 5a1 1 0 0 1 1-1h3v16H5a1 1 0 0 1-1-1V5Z" />
      <path d="M10 5a1 1 0 0 1 1-1h3v16h-3a1 1 0 0 1-1-1V5Z" />
      <path d="m16.5 5 3.4-.6a1 1 0 0 1 1.1.8L22.9 19a1 1 0 0 1-.8 1.1l-3.4.6" />
    </svg>
  );
}

function GoalsIcon() {
  return (
    <svg {...svgProps}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1" />
    </svg>
  );
}

function BriefIcon() {
  return (
    <svg {...svgProps}>
      <path d="M6 3h8l4 4v14H6z" />
      <path d="M14 3v4h4M9 12h6M9 16h6" />
    </svg>
  );
}
