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

- **Sources are always drawn.** An architect's desk lamp lights the main scene
  of a screen, a clip lamp lights a card that needs you, a wall sconce rides
  the navigation wall to the section you are in. Light never comes from
  nowhere.
- **A lamp burns only where there is something to do.** New words or a
  connected Kindle light the desk; due cards light the review card. When the
  work is done the lamp goes out and its corner falls into shadow, with a
  handwritten note saying why. By day the beams are gone and a lit subject
  keeps a faint warm wash.
- **Ray anatomy:** shade → soft volumetric cone (CSS clip-path anchored to the
  same corner as the drawing, blurred, `screen` blend at night) → warm pool
  where it lands → shadow cast away from the lamp. A few slow dust motes drift
  inside the cone. Components: `DeskLamp`, `ClipLamp`, `Sconce` in
  `src/components/light/`; the host is `.lamp-host`.
- **Light means focus.** The selected word, book or card sits in the pool; the
  rest of the room is in shadow (lower contrast, never unreadable).
- **One warm light colour** (`--lamp`, ~2700K amber, with `--lamp-beam` and
  `--lamp-hot` as its lighter tints). Everything else is graphite, paper and
  ink.
- **Transitions through light:** switching theme is a wall switch — the room
  dims, then relights, and lamps warm up with a brief flicker. Navigation
  between screens never blacks out.

## Pencil and paper

- Strokes are soft graphite: slightly irregular, double-stroked where emphasis
  is needed. Rules, frames and curls are fixed hand-placed SVG paths
  (`PencilRule`, `PencilFrame`, `CornerCurl`) stretched with non-scaling
  strokes, so they never jitter and never become perfect 1 px boxes. Larger
  drawings use the `#pencil-graphite` filter for grain.
- Typography borrows from books: dictionary entries for words
  (**lemma** *сущ.* — meaning), dot leaders for ledgers, handwritten notes in
  the margins.
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
  by nested bordered cards. A screen opens with `PageHead` (title, italic
  lede, tools) underlined in pencil.
- **Buttons** (`components/ui/button`): `default` is lit (lamp amber behind
  dark ink); `secondary` is drawn (`PencilFrame` outline); `ghost` is bare
  text; text buttons are underlined in pencil. Every button has hover (light
  warms), pressed (scale 0.97), focus (dashed ring) and disabled (faded) states.
- **Inputs and selects**: written on a pencil line that warms to the lamp
  colour on focus; selects get a drawn chevron. Icons sit on the line
  (`.screen-search`).
- **Switches**: the knob is a small bulb that lights up when on.
- **Badges**: handwritten notes in the margin (Caveat), never coloured pills.
- **Tables / lists**: rows separated by faint hand-drawn rules; the selected
  row is lit by a pool. Words read as dictionary entries, ledgers use dot
  leaders.
- **One lamp per screen**: home and Books — a desk lamp over the book on the
  desk; Words — a clip lamp over the chosen word's card; Review — a desk lamp
  over the index card, out when the session is done. Insights and Settings
  stay unlit.

## Do not

- Gradients that are not light. Glassmorphism. Neon. Purple.
- Icon-in-a-rounded-square card headers, uppercase micro-labels everywhere.
- Random colours per feature (Obsidian purple, Kindle blue): connectors are
  drawn objects in the same pencil.
- Long animations on things used dozens of times a day.
