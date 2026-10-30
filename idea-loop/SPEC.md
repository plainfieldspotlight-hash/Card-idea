# Idea Loop: Build Spec for Claude Code

Oct 30, 2026 · @Kevin

## What we're building

Idea Loop is a microlearning app where saved ideas come back on a schedule until you have actually used them. Deepstash wins on inspiration and loses on retention; this app flips that. The whole product is one loop: capture an idea, see it again at the right time, answer "where did you use this?", and watch your applied count grow.

Target user: a busy professional (you) who reads a lot, saves a lot, and remembers almost none of it a month later.

Scope for version 1: a single user, your own content, no social features, no curated library. Working name is Idea Loop; rename whenever.

## Core features

Each line is written so Claude Code can build it as a unit and you can test it in a minute.

1. **Capture an idea.** A form with four fields: the idea (one to three sentences), the source (book, article, podcast, person), a tag, and an optional "where I could use this" note. Saving takes under ten seconds.
2. **Import a source.** Paste a URL or upload a PDF or text file. The app calls the Claude API to pull out five to ten idea cards, each tied back to the source. You approve or delete each card before it is saved.
3. **Goals.** You create a goal ("Lead a treasury team well", "Launch the postcard business"). Every idea can be linked to one goal. The home screen groups ideas by goal, not by topic.
4. **Review schedule.** Every saved idea gets a next-review date. Spaced repetition: 1 day, 3 days, 7 days, 14 days, 30 days, 90 days. Each review asks two things: "Still useful?" (keep or archive) and "Did you use it?" (yes, not yet). A yes moves it up the schedule; a not yet keeps it close.
5. **Applied log.** When you answer yes, you type one line about where you used it. The idea stores a list of these. This is the app's real score: ideas applied, not ideas saved.
6. **Depth on demand.** Every card has an expand button that shows the original passage, surrounding context, and a counterpoint. For imported sources, Claude fills these in at import time. For manual ideas, they are optional fields.
7. **Weekly summary.** Every Sunday the app generates a short note: ideas saved, ideas applied, one idea worth revisiting. No streaks, no badges, no push nagging.
8. **Output.** Pick a goal or a tag and ask for a brief. Claude turns the selected ideas and applied notes into a one-page document (talking points for a 1:1, a post draft, a meeting prep sheet). Copy or download it.
9. **Search and filter.** By tag, goal, source, applied or not, due today.

## Data model

Five tables cover version 1. Every table has an id, created\_at, and updated\_at.

| Table | Fields | Notes |
| --- | --- | --- |
| sources | title, type (book, article, podcast, person, other), url, author, raw\_text | raw\_text holds imported content for depth on demand |
| goals | name, description, status (active, done, paused) | A goal has many ideas |
| ideas | text, context, counterpoint, source\_id, goal\_id, status (active, archived), review\_interval\_index, next\_review\_at, applied\_count | review\_interval\_index points into \[1, 3, 7, 14, 30, 90\] days |
| tags and idea\_tags | name; idea\_id, tag\_id | Many to many |
| applications | idea\_id, note, applied\_at | One row every time you say "yes, I used it" |

Review rule, in words: when you answer "used it", move review\_interval\_index up one and set next\_review\_at to today plus that interval. When you answer "not yet", keep the index and set next\_review\_at to today plus the current interval. When you archive, set status to archived and clear next\_review\_at.

## Recommended stack

Build it as a web app first. It works on your phone through the browser, deploys for free, and Claude Code is strongest here. A native app can come later once the loop proves itself.

| Layer | Choice | Why |
| --- | --- | --- |
| Framework | Next.js (App Router) with TypeScript | One codebase for pages and API routes; Claude Code knows it well |
| Database | SQLite via Prisma for local, Postgres on Supabase when you deploy | Start with zero setup; swap the connection string later |
| Styling | Tailwind CSS | Fast to iterate, mobile-friendly by default |
| AI | Claude API (claude-sonnet) for import extraction, counterpoints, and briefs | One key in a .env file |
| Auth | None in version 1, then Supabase Auth | Single user first |
| Hosting | Vercel free tier | Push to GitHub, it deploys |

You need: Node.js installed, a GitHub account, an Anthropic API key, and Claude Code. Total cost to run version 1 is a few dollars a month in API calls.

## Screens and user flow

Six screens. The app opens on Today, because the review is the point.

1. **Today.** Ideas due for review, one card at a time. Each card shows the idea, its source, and two buttons: Used it / Not yet, plus a small Archive link. "Used it" opens a one-line note field. Empty state says "Nothing due. Add an idea or import a source."
2. **Add.** The four-field capture form. Also a tab for Import: paste a URL or upload a file, then approve the extracted cards.
3. **Library.** All ideas, grouped by goal. Filters for tag, source, applied, archived. Tap a card to expand it.
4. **Idea detail.** Full card, context and counterpoint, the list of applied notes with dates, next review date, and edit and archive buttons.
5. **Goals.** List of goals with counts: ideas linked, ideas applied. Create and edit goals here.
6. **Brief.** Pick a goal or tag, pick a format (talking points, post draft, meeting prep), get a generated document you can copy or download as markdown.

Bottom navigation on mobile: Today, Add, Library, Goals, Brief. Weekly summary appears as a banner at the top of Today on Sundays.

## Build order

Six phases. Each one ends with something you can click on your phone. Do not start the next until the current one works; this is where solo app projects die.

1. **Phase 1, skeleton.** New Next.js project, Prisma with SQLite, the five tables, Tailwind, bottom nav with placeholder pages. Done when the app runs locally and you can tap between screens.
2. **Phase 2, capture and library.** The Add form and the Library screen with grouping by goal and filters. Done when you can save ten ideas by hand and find them.
3. **Phase 3, the review loop.** The Today screen, the spacing rule, the Used it / Not yet / Archive actions, the applications table. Done when an idea you saved yesterday shows up today and moves correctly after you answer.
4. **Phase 4, AI import.** URL and file import, Claude API extraction, the approve-or-delete step, context and counterpoint fields. Done when you can paste an article link and get five usable cards.
5. **Phase 5, briefs and weekly summary.** The Brief screen and the Sunday banner. Done when you can generate talking points from a goal and copy them.
6. **Phase 6, deploy.** GitHub repo, Vercel, Supabase Postgres, Supabase Auth with a single allowed email. Done when it loads on your phone from a real URL.

Use the app for two weeks after phase 3 before building phase 4. If you do not open it daily, the loop needs work and no amount of AI import will fix that.

## Prompts for Claude Code

Before the first prompt, save this whole document as a file named SPEC.md in an empty folder, open Claude Code in that folder, and start with the setup prompt. Each later prompt points back at the spec so you never have to re-explain the app.

**Setup**

```markdown
Read SPEC.md. Create a CLAUDE.md file that summarizes the product, the data model, the stack, and the build order in under 300 words, so you remember the project in future sessions. Then confirm you understand the review schedule rule by restating it.
```

**Phase 1**

```markdown
Read SPEC.md and CLAUDE.md. Build Phase 1: a new Next.js App Router project in TypeScript with Tailwind, Prisma with SQLite, the five tables from the data model, a seed script with two goals and five sample ideas, and a mobile bottom navigation with placeholder pages for Today, Add, Library, Goals, and Brief. Run it, fix any errors, and tell me the command to start it.
```

**Phase 2**

```markdown
Read SPEC.md. Build Phase 2: the Add screen with the four-field capture form (idea, source, tag, where I could use this) and goal picker, and the Library screen grouped by goal with filters for tag, source, applied, and archived. Tapping a card opens the Idea detail screen. Keep everything mobile-first. Show me how to test it.
```

**Phase 3**

```markdown
Read SPEC.md. Build Phase 3: the Today screen showing ideas where next_review_at is today or earlier, one card at a time, with Used it, Not yet, and Archive. Implement the spacing rule exactly as written in the data model section. Used it opens a one-line note field and writes to the applications table. Add a dev-only button that sets a chosen idea's next_review_at to today so I can test without waiting.
```

**Phase 4**

```markdown
Read SPEC.md. Build Phase 4: an Import tab on the Add screen. Accept a URL or a PDF or text upload, fetch or parse the text, send it to the Claude API (key in .env as ANTHROPIC_API_KEY) and ask for five to ten idea cards as JSON, each with text, context, and counterpoint. Show them as a list with approve and delete per card, then save the approved ones linked to a new sources row. Handle errors with a plain message, never a crash.
```

**Phase 5**

```markdown
Read SPEC.md. Build Phase 5: the Brief screen. Let me pick a goal or tag and a format (talking points, post draft, meeting prep), send the matching ideas and their applied notes to the Claude API, and display the result with copy and download-as-markdown buttons. Then add the Sunday weekly summary banner on Today: ideas saved this week, ideas applied this week, and one idea with the most not-yet answers.
```

**Phase 6**

```markdown
Read SPEC.md. Prepare for deployment: switch Prisma to Postgres using a DATABASE_URL env var, add Supabase Auth with email login and a single allowed email set in .env, create a .env.example, write a README with the exact steps to deploy on Vercel with Supabase, and commit everything to git. Walk me through what I need to click in Vercel and Supabase.
```

**When something breaks**

```markdown
Here is the error I see: [paste]. Read CLAUDE.md, find the cause, fix it, and explain in two sentences what went wrong.
```
