# Idea Loop

Saved ideas come back on a schedule until you have actually used them. See `SPEC.md` for the product spec and `CLAUDE.md` for the short project memory.

## Run it locally

```bash
cd idea-loop
npm install
npm run setup     # creates the SQLite database and seeds two goals + five ideas
npm run dev       # http://localhost:3000
```

Open it on your phone from the same Wi-Fi with the network URL that `next dev` prints.

## Useful scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Start the dev server |
| `npm run setup` | Run migrations and seed sample data |
| `npm run db:seed` | Re-seed (wipes and recreates sample data) |
| `npm run db:studio` | Browse the database in Prisma Studio |
| `npm run db:reset` | Drop and recreate the database |
| `npm run typecheck` / `npm run lint` / `npm run build` | Checks |

## Status

Phase 1 (skeleton) is done: Next.js App Router, Prisma + SQLite with the five tables, seed script, and a bottom nav with Today, Add, Library, Goals, and Brief. Today, Library, and Goals already read from the database. Everything else is a placeholder until its phase.
