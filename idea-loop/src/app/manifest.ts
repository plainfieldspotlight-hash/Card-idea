import type { MetadataRoute } from "next";

// Web app manifest: lets Android Chrome (and other browsers) install Idea Loop
// to the home screen and run it full screen like a native app.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Idea Loop",
    short_name: "Idea Loop",
    description: "Saved ideas come back on a schedule until you have used them.",
    id: "/",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#fafaf9",
    theme_color: "#0f766e",
    lang: "en",
    categories: ["productivity", "education"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Add an idea", url: "/add", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Library", url: "/library", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
    ],
  };
}
