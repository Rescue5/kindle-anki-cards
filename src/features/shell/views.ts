// The app's screens and how they map onto the navigation. Pure, so it is tested without a browser.

/** `triage` (Спорные) and `export` open from Слова and have no entry of their own in the navigation. */
export type View = "home" | "words" | "triage" | "export" | "settings";
export const VIEWS: readonly View[] = ["home", "words", "triage", "export", "settings"];

/** The navigation entries. The wall sconce shows which one holds the current view. */
export type NavView = "home" | "words" | "settings";
export const NAV_VIEWS: readonly NavView[] = ["home", "words", "settings"];

const NAV_OF: Record<View, NavView> = { home: "home", words: "words", triage: "words", export: "words", settings: "settings" };

export function navViewOf(view: View): NavView {
  return NAV_OF[view];
}

/** `?view=` opens a screen directly (browser previews, screenshots); anything unknown falls back to the home screen. */
export function parseView(search: string): View {
  const requested = new URLSearchParams(search).get("view");
  return (VIEWS as readonly string[]).includes(requested ?? "") ? (requested as View) : "home";
}
