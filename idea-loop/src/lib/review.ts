// Spaced-repetition schedule from SPEC.md. review_interval_index points here.
export const REVIEW_INTERVALS_DAYS = [1, 3, 7, 14, 30, 90] as const;

export function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

/** Next review date for a given interval index, clamped to the last interval. */
export function nextReviewDate(intervalIndex: number, from: Date = new Date()): Date {
  const clamped = Math.min(Math.max(intervalIndex, 0), REVIEW_INTERVALS_DAYS.length - 1);
  return addDays(from, REVIEW_INTERVALS_DAYS[clamped]);
}
