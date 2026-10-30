/* eslint-disable @next/next/no-img-element */
import { coverFor, type CoverIcon } from "@/lib/cover";

/**
 * Cover image for a goal or topic. Shows the user's image when there is one,
 * otherwise a generated gradient with an icon picked from the name.
 */
export function Cover({
  name,
  src,
  className = "",
  size = "md",
}: {
  name: string;
  src: string | null;
  className?: string;
  size?: "sm" | "md" | "lg";
}) {
  const iconSize = size === "sm" ? "h-5 w-5" : size === "md" ? "h-8 w-8" : "h-12 w-12";
  const textSize = size === "sm" ? "text-base" : size === "md" ? "text-2xl" : "text-4xl";

  if (src) {
    return (
      <div className={`relative overflow-hidden bg-border ${className}`}>
        <img src={src} alt="" className="absolute inset-0 h-full w-full object-cover" loading="lazy" />
      </div>
    );
  }

  const cover = coverFor(name);
  return (
    <div
      aria-hidden
      className={`relative flex items-center justify-center overflow-hidden text-white ${className}`}
      style={{ backgroundImage: `linear-gradient(135deg, ${cover.from}, ${cover.to})` }}
    >
      <div
        className="absolute -right-4 -top-6 h-24 w-24 rounded-full opacity-25"
        style={{ background: "white" }}
      />
      <div
        className="absolute -bottom-8 -left-3 h-20 w-20 rounded-full opacity-15"
        style={{ background: "white" }}
      />
      {cover.icon === "letter" ? (
        <span className={`relative font-semibold ${textSize}`}>{cover.letter}</span>
      ) : (
        <Icon name={cover.icon} className={`relative ${iconSize} drop-shadow`} />
      )}
    </div>
  );
}

function Icon({ name, className }: { name: CoverIcon; className: string }) {
  const p = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className,
  };
  switch (name) {
    case "people":
      return (
        <svg {...p}>
          <circle cx="9" cy="8" r="3.5" />
          <path d="M2.5 20a6.5 6.5 0 0 1 13 0" />
          <circle cx="17" cy="9" r="2.5" />
          <path d="M16 20h5.5a5 5 0 0 0-4-5" />
        </svg>
      );
    case "coin":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v10M9.5 9.5c0-1 1-1.5 2.5-1.5s2.5.6 2.5 1.6c0 2.4-5 1.4-5 3.9 0 1 1 1.6 2.5 1.6s2.5-.5 2.5-1.5" />
        </svg>
      );
    case "target":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="9" />
          <circle cx="12" cy="12" r="5" />
          <circle cx="12" cy="12" r="1" />
        </svg>
      );
    case "chat":
      return (
        <svg {...p}>
          <path d="M4 5h16v11H9l-5 4z" />
          <path d="M8 9h8M8 12.5h5" />
        </svg>
      );
    case "pen":
      return (
        <svg {...p}>
          <path d="m4 20 1-4L16.5 4.5a2.1 2.1 0 0 1 3 3L8 19z" />
          <path d="m14 7 3 3" />
        </svg>
      );
    case "heart":
      return (
        <svg {...p}>
          <path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" />
        </svg>
      );
    case "book":
      return (
        <svg {...p}>
          <path d="M4 5a2 2 0 0 1 2-2h14v16H6a2 2 0 0 0-2 2z" />
          <path d="M4 19a2 2 0 0 1 2-2h14M8 7h8" />
        </svg>
      );
    case "rocket":
      return (
        <svg {...p}>
          <path d="M12 3c3 2 5 6 5 10l-2 2H9l-2-2c0-4 2-8 5-10z" />
          <path d="M9 15l-3 3M15 15l3 3M12 15v5" />
          <circle cx="12" cy="9" r="1.5" />
        </svg>
      );
    case "compass":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="9" />
          <path d="m15.5 8.5-2 5-5 2 2-5z" />
        </svg>
      );
    case "calendar":
      return (
        <svg {...p}>
          <rect x="3" y="5" width="18" height="16" rx="2" />
          <path d="M3 10h18M8 3v4M16 3v4" />
        </svg>
      );
    case "bolt":
      return (
        <svg {...p}>
          <path d="M13 2 4 14h7l-1 8 9-12h-7z" />
        </svg>
      );
    case "leaf":
      return (
        <svg {...p}>
          <path d="M20 4c-9 0-15 5-15 12 0 2 1 4 1 4s9 1 13-6c2-3 1-10 1-10z" />
          <path d="M5 20c3-5 7-8 12-11" />
        </svg>
      );
    default:
      return null;
  }
}
