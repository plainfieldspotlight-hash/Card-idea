-- AlterTable
ALTER TABLE "goals" ADD COLUMN "image_data" BLOB;
ALTER TABLE "goals" ADD COLUMN "image_mime" TEXT;
ALTER TABLE "goals" ADD COLUMN "image_url" TEXT;

-- AlterTable
ALTER TABLE "tags" ADD COLUMN "image_data" BLOB;
ALTER TABLE "tags" ADD COLUMN "image_mime" TEXT;
ALTER TABLE "tags" ADD COLUMN "image_url" TEXT;
