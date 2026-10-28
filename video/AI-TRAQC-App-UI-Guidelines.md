# AI TRAQC — App UI Guidelines

How to apply the AI TRAQC design system to an app's graphical user interface. Hand this file to a designer, a developer, or an AI coding assistant.

---

## 1. Brand character
- Public, credible, optimistic. Technical and precise, never hype.
- German first. Address users formally with "Sie". Use gender-inclusive forms ("Teilnehmende").
- No emoji. Line icons only.
- Signature device: the **channel rule**, a bar split into equal thirds of blue / teal / red.

## 2. Logo
Files included: `aitraqc-logo-full.png` (with claim) and `aitraqc-logo-compact.png` (app bars, splash, favicons).
- Place on white or very light surfaces. On navy, use a white container or a white version if one exists.
- Clear space: at least the height of the "A" on every side.
- Minimum height: 24px (compact), 40px (full).
- Do not recolour, stretch, rotate, add shadows, or re-type the wordmark.

## 3. Colour
Core palette
| Role | Token | Hex |
|---|---|---|
| Primary (actions, links, active states) | `--traqc-blue` | `#004F9E` |
| Secondary (success, progress, positive) | `--traqc-teal` | `#279D7E` |
| Accent (errors, destructive, sparing highlights) | `--traqc-red` | `#E30614` |
| Deep ink / dark surfaces | `--traqc-navy` | `#00314E` |
| Rare (illustrative only) | `--traqc-purple` | `#8A3488` |

Neutrals (cool grey toward navy): `#10171D` 900 · `#1F2A33` 800 · `#3A474F` 700 · `#5A6670` 600 · `#7C8791` 500 · `#A3ADB5` 400 · `#C8CED3` 300 · `#E0E4E8` 200 · `#EEF1F3` 100 · `#F6F8F9` 050.

Semantic use
- Headings: navy `#00314E`. Body text: grey-800 `#1F2A33`. Secondary text: grey-600 `#5A6670`.
- Page background: white. Subtle panels: `#F6F8F9`. Sunken areas / inputs disabled: `#EEF1F3`.
- Borders: `#E0E4E8` (subtle), `#C8CED3` (default), `#A3ADB5` (strong).
- Primary button hover `#003D78`, pressed `#00314E`. Danger hover `#A80410`.
- Status: success `#279D7E`, warning `#E0A400`, danger `#E30614`, info `#004F9E`.
- Tints for backgrounds of badges/alerts: blue-050 `#EEF4FA`, teal-050 `#EEF8F4`, red-050 `#FDECED`.
- Text contrast must be at least 4.5:1. Never put grey text on navy; use white.

## 4. Typography
Substitute Google Fonts (swap for licensed brand fonts when available):
- **Barlow Semi Condensed**: headings, numbers in stats, app bar titles. Weight 700–800, letter-spacing −0.02em, line-height 1.05–1.15.
- **Barlow**: body and UI. Weight 400–500, line-height 1.5 (UI) to 1.7 (long text).
- **IBM Plex Mono**: codes, IDs, data values.

Scale (px): 11 micro · 12 caption · 13 small UI · 14 secondary · **16 body** · 18 lead · 22 card title · 28 h4 · 36 h3 · 48 h2 · 60 h1.
- Mobile: body 16, screen title 22–28.
- Eyebrows / section labels: UPPERCASE, 12–13px, weight 600, letter-spacing 0.12em, blue or teal.
- Emphasis inside a light line uses bold weight, mirroring the claim "Getting **people** ready for AI".
- German number format: `1.240`, `94 %`.

## 5. Spacing, shape, layout
- 4px grid: 4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48 · 64 · 80 · 96.
- Radii: tags 3px · buttons/inputs 6px · cards 10px · sheets/modals 16px. Pills only for badges, switches, progress bars.
- Control heights: 32 (small) · 40 (default) · 48 (large, and minimum for touch targets on mobile — 44px absolute minimum).
- Left-aligned layouts, generous whitespace, clear hierarchy. Max content widths 640 / 960 / 1200 / 1400px.

## 6. Elevation and borders
- Cards: white, 1px `#E0E4E8` border, soft shadow, optional 4–7px channel rule on top.
- Shadows are navy-tinted and soft:
  - sm `0 1px 3px rgba(0,49,78,.08), 0 1px 2px rgba(0,49,78,.06)`
  - md `0 4px 12px rgba(0,49,78,.10)` (raised cards, dropdowns)
  - lg `0 10px 28px rgba(0,49,78,.12)` (modals, sheets)
- No black drop shadows, no glassmorphism. A blurred 90 % white is allowed for sticky headers only.

## 7. Interaction states
- Hover: darken the same hue (buttons); faint blue-050 wash (ghost/secondary); cards lift 2px with a larger shadow.
- Pressed: move 1px down. No colour flash.
- Focus: 3px ring `rgba(0,79,158,.35)`. Never remove it.
- Disabled: grey-100 background, grey-500 text, no shadow.
- Motion: 120ms (small), 200ms (default), 320ms (panels). Easing `cubic-bezier(0.2,0,0.2,1)`. No bounce or spring.

## 8. Components
Available in the design system: Logo, ChannelRule, Eyebrow, Icon, Button, IconButton, Input, Textarea, Select, Checkbox, Radio, Switch, Card, Badge, Tag, Avatar, Stat, Progress, Alert, Tabs, Breadcrumb.

Button variants
- Primary: blue fill, white text. One per screen area.
- Secondary: white, 1px blue border, blue text.
- Ghost: no border, blue text.
- Danger: red fill, white text. Destructive actions only.
- Sizes 32 / 40 / 48px.

Inputs: 40px high, 1px grey-300 border, 6px radius, label above in 14px medium, helper text 12–13px grey-600, error text and border in red.

Badges/tags: tinted background (050) with full-strength text in the same hue.

Progress: pill track grey-100, fill teal or blue; animate width only.

## 9. Icons
- Lucide line icons, ~1.75px stroke, 16 / 20 / 24px.
- Colour with blue, teal, navy or grey; red only for destructive or errors.
- Common: graduation-cap, users, calendar, book-open, award, brain, arrow-right, search, check-circle.

## 10. Backgrounds and imagery
- Default UI surfaces stay white and grey-050.
- Particle "dot-flow" wave: only for splash, onboarding and empty-state heroes, always under a white protection gradient so text stays legible.
- Navy fields with a faint particle strip: for stat bands, section dividers, or a dark header.
- Abstract, data-driven imagery. No stock photography look.

## 11. App structure suggestions
- App bar: white, compact logo left, screen title in Barlow Semi Condensed 700, 1px bottom border.
- Navigation: bottom tab bar (mobile) or left sidebar (desktop); active item in blue with a 2–3px indicator.
- Lists: 1px dividers, 48–56px rows, chevron right for drill-in.
- Empty states: line icon, short headline, one primary action.
- Footer / about screen: funding lockup "Kofinanziert von der Europäischen Union" and partner logos.

## 12. Code setup (web)
```html
<link rel="stylesheet" href="styles.css"> <!-- imports all tokens -->
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=Barlow+Semi+Condensed:wght@600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
```
```css
:root {
  --traqc-blue:#004F9E; --traqc-teal:#279D7E; --traqc-red:#E30614;
  --traqc-navy:#00314E; --traqc-purple:#8A3488;
  --radius-sm:3px; --radius-md:6px; --radius-lg:10px; --radius-xl:16px;
  --ease-standard:cubic-bezier(0.2,0,0.2,1);
}
.channel-rule { height:5px; background:linear-gradient(90deg,
  #004F9E 0 33.33%, #279D7E 33.33% 66.66%, #E30614 66.66% 100%); }
```

For a native app (iOS/Android/Flutter), map the hex values and sizes above into your theme files one-to-one.

## Caveats
- Fonts and icons are substitutions until licensed brand assets are provided.
- Colours were sampled from logo images; confirm against an official brand sheet if one exists.
