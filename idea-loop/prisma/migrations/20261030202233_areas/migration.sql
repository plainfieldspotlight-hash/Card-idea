-- CreateTable
CREATE TABLE "areas" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "sort_order" INTEGER NOT NULL DEFAULT 0,
    "image_url" TEXT,
    "image_data" BLOB,
    "image_mime" TEXT,
    "created_at" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" DATETIME NOT NULL
);

-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_goals" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "status" TEXT NOT NULL DEFAULT 'active',
    "area_id" TEXT,
    "image_url" TEXT,
    "image_data" BLOB,
    "image_mime" TEXT,
    "created_at" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" DATETIME NOT NULL,
    CONSTRAINT "goals_area_id_fkey" FOREIGN KEY ("area_id") REFERENCES "areas" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);
INSERT INTO "new_goals" ("created_at", "description", "id", "image_data", "image_mime", "image_url", "name", "status", "updated_at") SELECT "created_at", "description", "id", "image_data", "image_mime", "image_url", "name", "status", "updated_at" FROM "goals";
DROP TABLE "goals";
ALTER TABLE "new_goals" RENAME TO "goals";
CREATE INDEX "goals_area_id_idx" ON "goals"("area_id");
CREATE TABLE "new_ideas" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "text" TEXT NOT NULL,
    "context" TEXT,
    "counterpoint" TEXT,
    "use_note" TEXT,
    "source_id" TEXT,
    "goal_id" TEXT,
    "area_id" TEXT,
    "status" TEXT NOT NULL DEFAULT 'active',
    "review_interval_index" INTEGER NOT NULL DEFAULT 0,
    "next_review_at" DATETIME,
    "applied_count" INTEGER NOT NULL DEFAULT 0,
    "created_at" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" DATETIME NOT NULL,
    CONSTRAINT "ideas_source_id_fkey" FOREIGN KEY ("source_id") REFERENCES "sources" ("id") ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT "ideas_goal_id_fkey" FOREIGN KEY ("goal_id") REFERENCES "goals" ("id") ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT "ideas_area_id_fkey" FOREIGN KEY ("area_id") REFERENCES "areas" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);
INSERT INTO "new_ideas" ("applied_count", "context", "counterpoint", "created_at", "goal_id", "id", "next_review_at", "review_interval_index", "source_id", "status", "text", "updated_at", "use_note") SELECT "applied_count", "context", "counterpoint", "created_at", "goal_id", "id", "next_review_at", "review_interval_index", "source_id", "status", "text", "updated_at", "use_note" FROM "ideas";
DROP TABLE "ideas";
ALTER TABLE "new_ideas" RENAME TO "ideas";
CREATE INDEX "ideas_next_review_at_idx" ON "ideas"("next_review_at");
CREATE INDEX "ideas_goal_id_idx" ON "ideas"("goal_id");
CREATE INDEX "ideas_area_id_idx" ON "ideas"("area_id");
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;

-- CreateIndex
CREATE UNIQUE INDEX "areas_name_key" ON "areas"("name");

-- Default life areas. Fixed ids so seeds and docs can refer to them.
INSERT INTO "areas" ("id", "name", "description", "sort_order", "created_at", "updated_at") VALUES
  ('area_career',    'Career',             'Work, craft, and the next role.',                1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
  ('area_family',    'Family',             'Partner, kids, parents, home.',                  2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
  ('area_influence', 'Influencing others', 'Persuading, leading, communicating.',            3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
  ('area_hobbies',   'Hobbies',            'Side projects and things done for their own sake.', 4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
  ('area_friends',   'Friends',            'Keeping and deepening friendships.',             5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
  ('area_health',    'Health',             'Body, sleep, energy.',                           6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
  ('area_money',     'Money',              'Earning, saving, investing.',                    7, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
  ('area_learning',  'Learning',           'Reading, courses, skills.',                      8, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
