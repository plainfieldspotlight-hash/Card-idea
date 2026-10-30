// Deterministic default cover art for goals and topics. Every goal and tag
// gets an image even before the user uploads one: a gradient picked from the
// name's hash plus an icon chosen from keywords in the name.

export type CoverIcon =
  | "people"
  | "coin"
  | "target"
  | "chat"
  | "pen"
  | "heart"
  | "book"
  | "rocket"
  | "compass"
  | "calendar"
  | "bolt"
  | "leaf"
  | "briefcase"
  | "megaphone"
  | "palette"
  | "letter";

const PALETTES: [string, string][] = [
  ["#0f766e", "#2dd4bf"], // teal
  ["#1d4ed8", "#60a5fa"], // blue
  ["#7c3aed", "#c4b5fd"], // violet
  ["#be185d", "#f9a8d4"], // pink
  ["#c2410c", "#fdba74"], // orange
  ["#a16207", "#fde047"], // amber
  ["#15803d", "#86efac"], // green
  ["#0e7490", "#67e8f9"], // cyan
  ["#4338ca", "#a5b4fc"], // indigo
  ["#b91c1c", "#fca5a5"], // red
];

const ICON_KEYWORDS: [CoverIcon, RegExp][] = [
  ["megaphone", /\b(influenc|persua|negotiat|communicat|speak|pitch|storytell)/i],
  ["briefcase", /\b(career|work|job|role|promotion|profession|office)/i],
  ["palette", /\b(hobb|craft|music|art\b|paint|photo|draw|cook|bake|game|guitar|piano)/i],
  ["people", /\b(manag|lead|team|people|hire|1:1|one.on.one|coach|mentor|culture|friend|social|network)/i],
  ["coin", /\b(money|price|pricing|cash|treasury|finance|budget|revenue|cost|invest|sales?)\b/i],
  ["target", /\b(focus|goal|priorit|strateg|plan)/i],
  ["chat", /\b(customer|discover|interview|talk|conversation|feedback|user|listen)/i],
  ["pen", /\b(writ|post\b|blog|essay|newsletter|draft|copy|story)/i],
  ["heart", /\b(health|run|marathon|fitness|sleep|gym|family|relationship|love)/i],
  ["book", /\b(learn|read|book|study|course|research|knowledge)/i],
  ["rocket", /\b(launch|startup|business|ship|growth|market|product|postcard)/i],
  ["compass", /\b(decision|decide|judg|choice|bet|risk)/i],
  ["calendar", /\b(meeting|schedule|week|day|habit|routine|time)/i],
  ["bolt", /\b(energy|speed|fast|momentum|motivat|productiv)/i],
  ["leaf", /\b(garden|nature|calm|mind|slow|rest|patien)/i],
];

export function hashString(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function coverFor(name: string): { from: string; to: string; icon: CoverIcon; letter: string } {
  const [from, to] = PALETTES[hashString(name.toLowerCase()) % PALETTES.length];
  const match = ICON_KEYWORDS.find(([, re]) => re.test(name));
  const letter = (name.trim()[0] ?? "?").toUpperCase();
  return { from, to, icon: match ? match[0] : "letter", letter };
}

type Imaged = { id: string; imageUrl: string | null; imageData: Uint8Array | null; updatedAt: Date };

export type ImageKind = "goal" | "tag" | "area";

/** The image to show for a goal, tag or area: the user's own if set, otherwise null (use the default cover). */
export function imageSrc(kind: ImageKind, row: Imaged): string | null {
  if (row.imageUrl) return row.imageUrl;
  if (row.imageData) return `/images/${kind}/${row.id}?v=${row.updatedAt.getTime()}`;
  return null;
}
