import { useCallback, useEffect, useRef, useState } from "react";

const SEEN_KEY = "kindle-cards.fox-tour.v1.seen";

export function useFoxTour(initialLibraryEmpty: boolean | null, onHome: boolean) {
  const [open, setOpen] = useState(false);
  const checked = useRef(false);
  const start = useCallback(() => {
    checked.current = true;
    try {
      window.localStorage.setItem(SEEN_KEY, "1");
    } catch {
      // Storage can be disabled. The current window still remembers this visit.
    }
    setOpen(true);
  }, []);

  useEffect(() => {
    if (checked.current || initialLibraryEmpty === null) return;
    checked.current = true;
    if (!initialLibraryEmpty || !onHome) return;

    try {
      if (window.localStorage.getItem(SEEN_KEY) === "1") return;
    } catch {
      // Keep the first-run guide available if storage cannot be read.
    }
    start();
  }, [initialLibraryEmpty, onHome, start]);

  return { open, start, dismiss: () => setOpen(false) };
}
