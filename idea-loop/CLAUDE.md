# Idea Loop

Short project memory. SPEC.md has the full spec.

## Product
Single-user microlearning app. Saved ideas come back on a schedule until you have used them: capture, review at the right time, answer "where did you use this?", watch the applied count grow. No social, no curated library, no streaks.

## Data model (Prisma, `prisma/schema.prisma`)
Six models, snake_case tables, each with id, created_at, updated_at.
- `sources`: title, type (book|article|podcast|person|other), url, author, raw_text
- `goals`: name, description, status (active|done|paused)
- `ideas`: text, context, counterpoint, use_note, source_id, goal_id, status (active|archived), review_interval_index, next_review_at, applied_count
- `tags` + `idea_tags`: many to many
- `applications`: idea_id, note, applied_at (one row per "yes, I used it")

## Review rule
Intervals are `[1, 3, 7, 14, 30, 90]` days (`src/lib/review.ts`). "Used it": index + 1, next_review_at = today + that interval, add an applications row, applied_count + 1. "Not yet": keep index, next_review_at = today + current interval. "Archive": status = archived, next_review_at = null.

## Stack
Next.js 16 App Router (Cache Components on), TypeScript, Tailwind v4, Prisma 7 + SQLite via better-sqlite3 adapter (Supabase Postgres in Phase 6), Claude API from Phase 4. Client generated to `src/generated/prisma` (gitignored), wrapped in `src/lib/db.ts`.

## Conventions
- Any server component that reads the DB: `await connection()` first and wrap it in `<Suspense>`, otherwise Next prerenders the query at build time.
- Mobile first. Bottom nav: Today, Add, Library, Goals, Brief. Opens on Today.
- Commands: `npm run dev`, `npm run setup` (migrate + seed), `npm run db:seed`, `npm run typecheck`, `npm run lint`, `npm run build`.

## Build order
1. Skeleton (done) 2. Capture + Library 3. Review loop 4. AI import 5. Briefs + weekly summary 6. Deploy. Finish each phase before the next. Use the app for two weeks after Phase 3 before Phase 4.
