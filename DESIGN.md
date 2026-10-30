# Design: Night Reading

The visual world of Kindle Cards. Every screen, component and new feature
follows this document; tokens live in `src/design/` and `src/index.css`.

## The idea

A room at night, a book open under a lamp. The interface is drawn in soft
pencil on paper that is mostly in shadow. **Light is the signature**: lamps and
their rays decide what you look at, where attention goes, and how the app moves
between states. The day theme is the same room by daylight — pencil on paper,
the lamps unlit but still drawn.

The app is a daily tool (Impeccable "Operate" mode): drama lives in light and a
few rare moments; everyday actions stay fast, quiet and precise.

## Light (the signature)

- **Sources are always drawn.** A desk lamp lights the main scene of a screen,
  a floor lamp stands at the edge of the room, a small sconce lights the
  navigation. Light never comes from nowhere.
- **Ray anatomy:** shade → soft volumetric cone (layered gradients, blurred,
  masked, `screen` blend at night) → warm pool where it lands → soft shadow
  behind lit objects. A few slow dust motes drift inside the cone.
- **Light means focus.** The selected word, book or card sits in the pool; the
  rest of the room is in shadow (lower contrast, never unreadable).
- **One warm light colour** (`--lamp`, ~2700K amber). Everything else is
  graphite, paper and ink.
- **Transitions through light:** switching theme is a lamp switch (pull cord /
  click) — the room dims, then relights. Opening a card or review session
  brightens its lamp. Navigation between screens is a short dim (≤180 ms),
  never a long blackout.

## Pencil and paper

- Strokes are soft graphite: slightly irregular, double-hatched where emphasis
  is needed. Borders and dividers are drawn with `roughjs` (fixed seed per
  element so they don't jitter between renders) — never perfect 1 px boxes.
- Flourishes (curls, small vines, corner ornaments) mark headings, section
  breaks and empty states. They are sparse: at most one per region.
- Paper has a faint grain; at night it reads as dark paper under low light.
- Illustrations (lamps, books, shelves) are line drawings in the same pencil,
  never photos or glossy 3D.

## Colour

| Token | Night | Day | Use |
| --- | --- | --- | --- |
| `--paper` | deep blue-black graphite | warm off-white | background |
| `--ink` | soft chalk white | graphite | primary text |
| `--pencil` | muted grey | mid grey | secondary text, strokes |
| `--lamp` | warm amber light | warm amber (sparingly) | light, focus, primary action |
| `--shadow` | near black | soft grey | cast shadows |

No other accent colours. State colours (error, success) are desaturated and
drawn as pencil marks (underline, circle, cross-out) rather than coloured pills.

## Type

- **Literata** (variable, designed for e-reading): all reading text, headings,
  words, contexts. Optical sizes for display headings.
- **Caveat**: handwritten notes "in the margins" only — hints, counts written
  next to things, empty-state captions. Never for controls or body text.
- One scale for every screen (see `--text-*` tokens). No 11 px grey text: the
  minimum is 12 px with sufficient contrast in both themes.

## Motion

- Custom curves: `--ease-out: cubic-bezier(0.23, 1, 0.32, 1)` for entering,
  `--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1)` for moving on screen.
- Frequent actions (typing in search, selecting rows, list navigation): no
  animation beyond an instant light change.
- Occasional actions (theme switch, opening review, sync finished): one
  purposeful light transition, 200–600 ms.
- Ambient motion (dust motes, a rare lamp flicker): slow, subtle, paused when
  the window is hidden, removed under `prefers-reduced-motion`.
- Animate only `transform`, `opacity` and filters on small layers.

## Components

- **Surfaces**: few boxes. Regions are separated by drawn rules and light, not
  by nested bordered cards.
- **Buttons**: primary = lit (amber pool behind ink text, pencil outline);
  secondary = pencil outline; text buttons = underlined in pencil. Every button
  has hover (light warms), pressed (scale 0.97), focus (pencil ring) and
  disabled (faded graphite) states.
- **Inputs and selects**: drawn underline or rough box, custom chevrons; no
  native-looking controls.
- **Tables / lists**: rows separated by faint hand-drawn rules; the selected
  row is lit.

## Do not

- Gradients that are not light. Glassmorphism. Neon. Purple.
- Icon-in-a-rounded-square card headers, uppercase micro-labels everywhere.
- Random colours per feature (Obsidian purple, Kindle blue): connectors are
  drawn objects in the same pencil.
- Long animations on things used dozens of times a day.
