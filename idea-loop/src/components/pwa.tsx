"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui";

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

const DISMISS_KEY = "idea-loop:install-dismissed";

/** Registers the service worker in production builds. Renders nothing. */
export function ServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* offline support is a nice-to-have; the app works without it */
    });
  }, []);
  return null;
}

/**
 * "Install app" banner for Android Chrome and other browsers that fire
 * beforeinstallprompt. Hidden once installed or dismissed.
 */
export function InstallBanner() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      ("standalone" in navigator && (navigator as { standalone?: boolean }).standalone === true);
    let dismissed = false;
    try {
      dismissed = localStorage.getItem(DISMISS_KEY) === "1";
    } catch {}
    if (standalone || dismissed) return;

    const onPrompt = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BeforeInstallPromptEvent);
      setVisible(true);
    };
    const onInstalled = () => setVisible(false);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (!visible || !deferred) return null;

  const dismiss = () => {
    setVisible(false);
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {}
  };

  const install = async () => {
    await deferred.prompt();
    const { outcome } = await deferred.userChoice;
    if (outcome === "accepted") setVisible(false);
    else dismiss();
  };

  return (
    <div role="region" aria-label="Install Idea Loop" className="mb-5 flex items-center gap-3 rounded-2xl border border-accent/40 bg-accent/10 p-3">
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-medium">Put Idea Loop on your home screen</p>
        <p className="text-xs text-muted">Opens full screen, no browser bar.</p>
      </div>
      <Button type="button" onClick={install} className="min-h-10 shrink-0">
        Install
      </Button>
      <button type="button" onClick={dismiss} aria-label="Dismiss" className="min-h-10 shrink-0 px-2 text-muted hover:text-foreground">
        ✕
      </button>
    </div>
  );
}
