# DESIGN.md — Induduzo staff portal

The design system is not invented here. It is the one built in Figma
(`Induduzo - Staff Portal`, 39 screens) and mirrored from
`Documents/Induduzo-Figma`. Figma is the source of truth; this file is how it
lands in `portal/src/index.css`.

## Colour

Hex, not OKLCH, and `#FFFFFF` is a real token. That is deliberate: these exact
values are already bound as Figma variables across 39 screens and shipped in the
public site's tokens. Matching the built system beats a cleaner colour space.

| Token | Value | Used for |
|---|---|---|
| `navy` | `#0B1B2B` | Portal navigation, primary buttons, headings |
| `navHover` | `#203447` | Active navigation item, search field on navy |
| `ink` | `#182D3B` | Body text |
| `muted` | `#586674` | Secondary text, column headings |
| `subtle` | `#83909C` | Placeholder, disabled text |
| `gold` | `#C9A24B` | Accent. Brand mark, active nav label, focus ring |
| `paper` | `#F3F5F6` | Page background |
| `white` | `#FFFFFF` | Card and input surfaces |
| `line` | `#DDE3E8` | Borders and dividers |
| `soft` | `#E9EEF2` | Disabled surfaces, neutral badge |
| `warm` | `#F9F5EB` | Selected state |
| `green` / `greenSoft` | `#276249` / `#EAF4ED` | Positive, handled |
| `amber` / `amberSoft` | `#825C17` / `#FCF3DD` | Due, needs attention |
| `red` / `redSoft` | `#AA3E3B` | `#FBEDEC` | Overdue, error |

**Strategy: restrained.** Tinted neutrals carry the surface; gold is the single
accent and stays under 10%. Status colour is the exception and is earned, never
decorative. The public marketing site's `--brand` red (`#b7352f`) does **not**
appear in the portal.

Status is never carried by colour alone. Every badge has a text label, because
an overdue call must read as overdue in greyscale.

## Type

Two families. Source Serif 4 carries the human voice, Source Sans 3 the
operational detail. That split is the whole typographic idea: a person's name is
serif, their reference number is sans.

| Style | Font | Size / line height |
|---|---|---|
| Display | Serif SemiBold | 52 / 60 |
| Heading | Serif SemiBold | 32 / 40 |
| Title | Serif SemiBold | 24 / 32 |
| Section | Sans SemiBold | 22 / 28 |
| Body | Sans Regular | 16 / 24 |
| Label | Sans SemiBold | 16 / 24 |
| Small | Sans Regular | 14 / 20 |
| Micro | Sans SemiBold | 12 / 16, `letter-spacing: 0.65px`, uppercase |

Ratio between steps stays at or above 1.25. Micro is the only tracked style and
is used for column headings and field labels.

## Space and shape

Spacing scale: `0 4 8 12 16 20 24 32 40 48 64`. Radius: `0 8 12 16 999`.
Cards use 12, buttons and inputs 8, pills 999.

One elevation only, `Lift`: `0 4px 16px rgba(11,27,43,0.08)`. Used on nothing by
default. Borders do the work; shadow is for things that genuinely float.

Desktop is 1440 wide with a 1376 content column. Mobile is 390.

## Components

Four sets, 17 variants, all with editable text in Figma.

- **Button** — Primary, Secondary, Ghost, Selected, Danger, Disabled, Focus,
  Loading. 48px minimum height, 20px horizontal padding. Primary is navy and is
  reserved for the single next action on the screen.
- **Badge** — Neutral, Success, Due, Overdue. Pill, 999 radius, text always present.
- **Field** — Default, Focus, Error. Persistent label above, 48px input, hint
  line below that is reserved even when empty so the layout does not jump.
- **Portal navigation item** — Default, Active. Active is `navHover` with a gold label.

## Rules

1. Never hard-code a hex in a component. Tokens only.
2. Light only. No dark mode, no theme switching.
3. 48px minimum interactive target.
4. One primary action per screen.
5. Focus is always visible: 2px navy border plus a 3px gold ring.
6. Labels are persistent. Placeholder-only fields are not acceptable.
7. Errors state what happened and what to do, and never discard typed input.
