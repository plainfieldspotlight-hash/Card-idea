import "dotenv/config";
import { PrismaClient } from "../src/generated/prisma/client";
import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";
import { nextReviewDate } from "../src/lib/review";

const url = (process.env.DATABASE_URL ?? "file:./dev.db").replace(/^file:/, "");
const prisma = new PrismaClient({ adapter: new PrismaBetterSqlite3({ url }) });

async function main() {
  // Wipe in dependency order so the seed is repeatable.
  await prisma.application.deleteMany();
  await prisma.ideaTag.deleteMany();
  await prisma.idea.deleteMany();
  await prisma.tag.deleteMany();
  await prisma.goal.deleteMany();
  await prisma.source.deleteMany();

  // Life areas. The migration inserts eight defaults with fixed ids; keep them
  // and make sure they exist on databases created another way.
  const defaultAreas = [
    ["area_career", "Career", "Work, craft, and the next role."],
    ["area_family", "Family", "Partner, kids, parents, home."],
    ["area_influence", "Influencing others", "Persuading, leading, communicating."],
    ["area_hobbies", "Hobbies", "Side projects and things done for their own sake."],
    ["area_friends", "Friends", "Keeping and deepening friendships."],
    ["area_health", "Health", "Body, sleep, energy."],
    ["area_money", "Money", "Earning, saving, investing."],
    ["area_learning", "Learning", "Reading, courses, skills."],
  ] as const;
  for (const [i, [id, name, description]] of defaultAreas.entries()) {
    // Keyed by id so a renamed default area is left alone instead of colliding.
    await prisma.area.upsert({
      where: { id },
      update: {},
      create: { id, name, description, sortOrder: i + 1 },
    });
  }

  const treasury = await prisma.goal.create({
    data: {
      name: "Lead a treasury team well",
      description: "Be the manager people want to work for, and keep cash boring.",
      areaId: "area_career",
    },
  });
  const postcards = await prisma.goal.create({
    data: {
      name: "Launch the postcard business",
      description: "First 100 paying customers for the Plainfield postcard line.",
      areaId: "area_hobbies",
    },
  });

  const highOutput = await prisma.source.create({
    data: { title: "High Output Management", type: "book", author: "Andrew Grove" },
  });
  const mom = await prisma.source.create({
    data: { title: "The Mom Test", type: "book", author: "Rob Fitzpatrick" },
  });
  const podcast = await prisma.source.create({
    data: {
      title: "How I Built This: Stacy's Pita Chips",
      type: "podcast",
      url: "https://www.npr.org/podcasts/510313/how-i-built-this",
    },
  });

  const tagNames = ["management", "1:1s", "customer-discovery", "pricing", "focus"];
  const tags = Object.fromEntries(
    await Promise.all(
      tagNames.map(async (name) => [name, await prisma.tag.create({ data: { name } })] as const),
    ),
  );

  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  const ideas = [
    {
      text: "A manager's output is the output of their team plus the teams they influence. Judge your week by that, not by your own tasks.",
      context:
        "Grove's central definition. He argues that a manager's own deliverables are a rounding error next to the leverage of good decisions, training, and information flow.",
      counterpoint:
        "In a small team the manager is often also the strongest individual contributor; refusing all personal output can slow the team down.",
      useNote: "Monthly self-review: list team outcomes first.",
      goalId: treasury.id,
      sourceId: highOutput.id,
      tags: ["management", "focus"],
      nextReviewAt: yesterday, // due now, so Today has something to show
    },
    {
      text: "Hold the 1:1 on the report's agenda, not yours. Your job in the meeting is to listen and ask one more question.",
      context: "Grove recommends the subordinate owns the agenda and the manager coaches.",
      counterpoint:
        "Some reports never raise the hard topics on their own. Keep a short list of questions you will ask if they do not.",
      useNote: "Next round of 1:1s.",
      goalId: treasury.id,
      sourceId: highOutput.id,
      tags: ["management", "1:1s"],
      nextReviewAt: today,
    },
    {
      text: "Ask about the past, not the future. 'When did you last buy a postcard?' beats 'Would you buy this postcard?'",
      context:
        "The core Mom Test rule: people lie about hypotheticals and are honest about what they already did.",
      counterpoint:
        "Past behaviour misses genuinely new categories. Pair it with watching what people do when offered the real thing.",
      useNote: "Farmers market conversations this weekend.",
      goalId: postcards.id,
      sourceId: mom.id,
      tags: ["customer-discovery"],
      nextReviewAt: today,
    },
    {
      text: "Price the first product high enough that a sale teaches you something. A free trial teaches you nothing.",
      context:
        "Stacy's Pita Chips started by selling, not sampling, so every transaction was real feedback.",
      counterpoint:
        "Early high prices can scare off the people you most need to learn from. Small paid pilots are a middle path.",
      useNote: "Set the first postcard pack price.",
      goalId: postcards.id,
      sourceId: podcast.id,
      tags: ["pricing"],
      nextReviewAt: nextReviewDate(1), // 3 days out
    },
    {
      text: "Protect two hours a week with no meetings for the one problem that matters most this quarter.",
      context: null,
      counterpoint: null,
      useNote: "Block Friday 8 to 10.",
      goalId: treasury.id,
      sourceId: null,
      tags: ["focus"],
      nextReviewAt: nextReviewDate(0), // tomorrow
    },
  ];

  for (const idea of ideas) {
    await prisma.idea.create({
      data: {
        text: idea.text,
        context: idea.context,
        counterpoint: idea.counterpoint,
        useNote: idea.useNote,
        goalId: idea.goalId,
        areaId: idea.goalId === treasury.id ? "area_career" : "area_hobbies",
        sourceId: idea.sourceId,
        nextReviewAt: idea.nextReviewAt,
        tags: {
          create: idea.tags.map((name) => ({ tagId: tags[name].id })),
        },
      },
    });
  }

  const counts = {
    areas: await prisma.area.count(),
    goals: await prisma.goal.count(),
    sources: await prisma.source.count(),
    ideas: await prisma.idea.count(),
    tags: await prisma.tag.count(),
  };
  console.log("Seeded:", counts);
}

main()
  .catch((err) => {
    console.error(err);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
