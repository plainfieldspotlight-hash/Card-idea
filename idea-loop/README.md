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

Phases 1 and 2 are done. Ideas belong to a life area (Career, Family, Influencing others, Hobbies, Friends, Health, Money, Learning, or your own) and optionally a goal within it. You can capture ideas on Add (idea, source, tag, goal, where you could use it), browse the Library grouped by area and goal with area, tag, source, applied and archived filters, open an idea's detail screen to edit, archive, restore or delete it, and create and edit goals. Every area, goal and topic has a cover image: a generated one by default, or your own upload or link, set from the goal's edit page or the topic's page. Today shows what is due; the review loop itself (Used it / Not yet) arrives in Phase 3. Brief is a placeholder until Phase 5.
