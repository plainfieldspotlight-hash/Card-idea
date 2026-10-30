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

## On your Android phone

Idea Loop is a Progressive Web App, so it installs like a native app without an app store.

1. Run `npm run dev` on your computer and open the network URL it prints (for example `http://192.168.1.20:3000`) in Chrome on your phone, on the same Wi-Fi. After Phase 6 this becomes the real https URL.
2. Chrome shows an "Install" banner on the Today screen, or use the browser menu and choose **Add to Home screen** / **Install app**.
3. It opens full screen with its own icon, bottom nav sized for thumbs, and an offline page when there is no connection.

For a Play Store listing later, wrap the deployed https URL as a Trusted Web Activity with [PWABuilder](https://www.pwabuilder.com) or Bubblewrap. No code changes are needed for that.

## Status

Phases 1 to 3 are done. Ideas belong to a life area (Career, Family, Influencing others, Hobbies, Friends, Health, Money, Learning, or your own) and optionally a goal within it. You can capture ideas on Add (idea, source, tag, goal, where you could use it), browse the Library grouped by area and goal with area, tag, source, applied and archived filters, open an idea's detail screen to edit, archive, restore or delete it, and create and edit goals. Every area, goal and topic has a cover image: a generated one by default, or your own upload or link, set from the goal's edit page or the topic's page. Today runs the review loop: one due idea at a time with Used it (plus a one-line note of where), Not yet, and Archive, following the 1, 3, 7, 14, 30, 90 day schedule. In development, an idea's detail page has a "Make due now" button so you can test without waiting. Brief is a placeholder until Phase 5.
