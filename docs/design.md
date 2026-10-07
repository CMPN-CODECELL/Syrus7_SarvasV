# DESIGN.md: Syrus Hackathon Design System (CodeCell++ · VESIT)

> **FOR THE AI READING THIS FILE**
> You are building a website that must look like the Syrus hackathon site. Treat this file as the single source of truth for visual design. Follow it literally.
> - Use the exact hex values, font names, sizes, spacing and effects below. Do not substitute "similar" colors or fonts.
> - Do NOT invent a new palette, add light mode, use rounded pill buttons, or use soft drop shadows. See Section 14.
> - Content (copy, dates, sponsors, FAQs) comes from the user. This file only defines **look and feel**.
> - Start from the **Starter CSS (Section 3)**, then build components from Section 8, sections from Section 9.
> - Before finishing, run the **Checklist (Section 15)**.
> - Values marked **[measured]** were read from the live site. Values marked **[spec]** are design decisions made to fill gaps (hover states, spacing, responsive). Treat both as binding.

---

## 1. Concept

**Star Wars deep-space cockpit.** Near-black void, opening-crawl yellow headlines, holographic cyan lead text, warm cream reading text. Lightsaber glows, hyperspace streaks, scanlines, HUD hairline frames, typewriter terminal text. Dark theme only.

Mood words: opening crawl · holo-HUD · lightsaber · hyperspace · sharp · glowing · cinematic · scroll-driven storytelling.

Reference stack (optional, you may use any): React + CSS Modules, Bootstrap 5 grid, React-Toastify. Plain HTML/CSS/JS or any framework is fine as long as visuals match.

---

## 2. Design Tokens

### 2.1 Colors [measured]

| Token | Hex | Use |
|---|---|---|
| `--void` | `#04050A` | Page background. Text on yellow buttons |
| `--panel` | `#12151B` | Card / panel fill |
| `--panel-border` | `#2A2F39` | Card borders, inset rings |
| `--crawl-yellow` | `#FFE81F` | h1/h2/h3, primary CTA fill, active borders, glows |
| `--holo-cyan` | `#5FD4F0` | Lead paragraphs, links, accent lines, ambient glow |
| `--cream` | `#E8E2D0` | Default body text, nav text |
| `--cream-muted` | `#B9B4A6` | Secondary text |
| `--steel` | `#8B8F98` | Meta / tertiary text |
| `--steel-dark` | `#4A4F59` | Subtle fills |
| `--amber` | `#E9A415` | Rare warning accent only |
| `--yellow-soft` | `#FFF3A0` | Highlight fill |
| `--yellow-hot` | `#FFFBE0` | Saber core |
| `--cyan-hot` | `#BEECFC` | Cyan glow core |
| `--white-warm` | `#FFFEF5` | Brightest highlight |

Alpha values [measured]: `rgba(4,5,10,.55)` fades/scanlines · `rgba(4,5,10,.72)` translucent panels/nav · `rgba(4,5,10,.92)` header overlay · `rgba(4,5,10,.97)` modal · `rgba(232,226,208,.18)` 2px dividers · `rgba(232,226,208,.30)` hairline borders · `rgba(232,226,208,.42)` inset rings / rule fills.

Status colors (toasts): info `#3498DB`, success `#07BC0C`, warning `#F1C40F`, error `#E74C3C`.

Color roles (ratio of use): cream text dominates, yellow for titles and action, cyan for lead copy and accents. Never use pure white for text.

### 2.2 Fonts [measured]

| Role | Family | Fallback |
|---|---|---|
| Display (hero, numerals, big buttons) | `"Star Jedi"` | `Impact, sans-serif` |
| Outline display (h2 section titles) | `"Star Jedi Hollow"` | `Impact, sans-serif` |
| Body, UI, nav, labels, h3 | `Oxanium` | `system-ui, -apple-system, "Segoe UI", sans-serif` |

**Font sourcing (you must handle this):**
- **Oxanium**: Google Fonts, weights 400, 500, 600, 700, 800.
  `<link href="https://fonts.googleapis.com/css2?family=Oxanium:wght@400;500;600;700;800&display=swap" rel="stylesheet">`
- **Star Jedi** and **Star Jedi Hollow**: free "Star Jedi" typeface (Boba Fonts) in solid and hollow variants. Files are not bundled here. Ask the user to supply `StarJedi.ttf` and `StarJediHollow.ttf` (or place them in `/assets/fonts/`), then load via `@font-face` (Section 3). Check the license before commercial use.
- If the files are unavailable, the fallback is `Impact` with `letter-spacing: .04em` and `text-transform: uppercase`. Tell the user the fonts are missing.

### 2.3 Type scale

| Element | Font | Size | Weight | Letter-spacing | Line-height | Case | Color |
|---|---|---|---|---|---|---|---|
| h1 hero [measured] | Star Jedi | 54.4px at ~1200px wide. Use `clamp(2.25rem, 5.5vw, 3.4rem)` [spec] | 400 | `.01em` | 1 | none | yellow |
| Big display / numerals [measured 34.5px, 23px] | Star Jedi | `clamp(1.6rem, 3.5vw, 2.15rem)` [spec] | 400 | `.01em` | 1 | none | yellow |
| h2 [measured] | Star Jedi Hollow | 32px (`2rem`) | 400 | `.02em` | 1.05 | none | yellow |
| h3 eyebrow [measured] | Oxanium | 13px | 700 | `.18em` | 1.2 | UPPERCASE | yellow |
| Lead p [measured] | Oxanium | 18.4px (`1.15rem`) | 500 | `.04em` | 1.6 | none | cyan |
| Body / nav [measured] | Oxanium | 16px | 400 | normal | 1.5 | none | cream |
| CTA link [measured] | Oxanium | 12px | 700 | `.14em` | 1 | UPPERCASE | void on yellow |
| Display button [measured] | Star Jedi | 21.6px | 400 | normal | 1 | none | yellow |
| Small meta [measured] | Oxanium | 12–13px | 500–600 | `.04–.1em` | 1.4 | optional upper | steel |
| Micro [measured] | Oxanium | 9–11px | 600 | `.14em` | 1.2 | UPPERCASE | steel |

Rules:
- Star Jedi is for short display text only. Never use for paragraphs.
- Star Jedi Hollow only for h2.
- Oxanium uppercase + wide tracking for every label, tag, CTA.
- Weights in use: 400 (most), 500, 600, 700, 800.

### 2.4 Shape & borders [measured]

- Corner radius: `1px` default, `2px` buttons, `3px` max. Asymmetric `2px 3px 3px 2px`, `2px 0 0 2px`, `0 4px 4px 0` for tab or bar pieces. `50%` only for dots, orbs, rings.
- Card border: `0.67px solid #2A2F39` plus `inset 0 0 0 1px #2A2F39`. (Use `1px` on screens where 0.67px renders badly.)
- HUD frame border: `0.67px solid rgba(232,226,208,.30)`.
- Divider: `2px solid rgba(232,226,208,.18)`.
- Active border: `1.33px solid #FFE81F`.

### 2.5 Glows (the only form of "elevation") [measured]

```css
--glow-frame:  0 0 0 5px rgba(4,5,10,.6), 0 0 28px rgba(95,212,240,.08);
--glow-yellow: 0 0 14px rgba(255,232,31,.45);
--glow-yellow-strong: 0 0 16px 5px rgba(255,232,31,.5);
--glow-yellow-xl: 0 0 22px 8px rgba(255,232,31,.45);
--glow-cyan:   0 0 8px rgba(95,212,240,.7);
--glow-saber:  0 0 2px 1px #FFFBE0, 0 0 8px 2px rgba(255,232,31,.9), 0 0 30px 7px rgba(255,232,31,.26);
--glow-orb-cyan: 0 0 10px 1px rgba(255,255,255,.9), 0 0 26px 5px rgba(95,212,240,.75), 0 0 70px 14px rgba(95,212,240,.35);
--text-glow-sm: 0 0 14px rgba(255,232,31,.28);
--text-glow:    0 0 18px rgba(255,232,31,.18);
--text-glow-lg: 0 0 36px rgba(255,232,31,.28);
--text-glow-hero: 0 0 10px rgba(255,232,31,.35), 0 0 42px rgba(255,232,31,.18);
```

### 2.6 Spacing & layout [spec]

- Base unit 4px. Scale: 4, 8, 12, 16, 24, 32, 48, 64, 96, 128.
- Section vertical padding: `96px` desktop, `64px` tablet, `48px` mobile.
- Card padding: `24px` (`16px` mobile). Card gap: `24px`.
- Container max-width `1200px`, side padding `24px` (`16px` mobile). Bootstrap 5 container/grid compatible.
- Breakpoints [measured]: `576 · 768 · 992 · 1200 · 1400px`.

---

## 3. Starter CSS (copy this first)

```css
/* ---------- fonts ---------- */
@font-face { font-family: "Star Jedi"; src: url("/assets/fonts/StarJedi.ttf") format("truetype"); font-display: swap; }
@font-face { font-family: "Star Jedi Hollow"; src: url("/assets/fonts/StarJediHollow.ttf") format("truetype"); font-display: swap; }
/* Oxanium: load via Google Fonts <link> (see 2.2) */

/* ---------- tokens ---------- */
:root {
  --void:#04050A; --panel:#12151B; --panel-border:#2A2F39;
  --crawl-yellow:#FFE81F; --holo-cyan:#5FD4F0;
  --cream:#E8E2D0; --cream-muted:#B9B4A6; --steel:#8B8F98; --steel-dark:#4A4F59; --amber:#E9A415;
  --yellow-soft:#FFF3A0; --yellow-hot:#FFFBE0; --cyan-hot:#BEECFC; --white-warm:#FFFEF5;

  --font-display:"Star Jedi", Impact, sans-serif;
  --font-outline:"Star Jedi Hollow", Impact, sans-serif;
  --font-body:Oxanium, system-ui, -apple-system, "Segoe UI", sans-serif;

  --r-1:1px; --r-2:2px; --r-3:3px;

  --glow-frame:0 0 0 5px rgba(4,5,10,.6), 0 0 28px rgba(95,212,240,.08);
  --glow-yellow:0 0 14px rgba(255,232,31,.45);
  --glow-yellow-strong:0 0 16px 5px rgba(255,232,31,.5);
  --glow-cyan:0 0 8px rgba(95,212,240,.7);
  --glow-saber:0 0 2px 1px #FFFBE0, 0 0 8px 2px rgba(255,232,31,.9), 0 0 30px 7px rgba(255,232,31,.26);
  --text-glow:0 0 18px rgba(255,232,31,.18);
  --text-glow-hero:0 0 10px rgba(255,232,31,.35), 0 0 42px rgba(255,232,31,.18);

  --section-pad:96px;
}

/* ---------- base ---------- */
*,*::before,*::after{ box-sizing:border-box; }
html{ scroll-behavior:smooth; }
body{
  margin:0; background:var(--void); color:var(--cream);
  font-family:var(--font-body); font-size:16px; line-height:1.5;
  -webkit-font-smoothing:antialiased; overflow-x:hidden;
}
/* ambient nebula, fixed behind everything */
body::before{
  content:""; position:fixed; inset:0; z-index:-2; pointer-events:none;
  background:
    radial-gradient(70% 45% at 50% 115%, rgba(95,212,240,.07), transparent 70%),
    radial-gradient(60% 35% at 15% -5%,  rgba(255,232,31,.035), transparent 70%),
    radial-gradient(50% 40% at 90% 30%,  rgba(95,212,240,.03),  transparent 70%);
}
/* optional scanline overlay */
body::after{
  content:""; position:fixed; inset:0; z-index:-1; pointer-events:none; opacity:.35;
  background:repeating-linear-gradient(90deg, rgba(4,5,10,.55) 0 2px, transparent 2px 4px);
}
a{ color:var(--holo-cyan); text-decoration:none; }
a:hover{ text-shadow:var(--glow-cyan); }
::selection{ background:var(--crawl-yellow); color:var(--void); }

h1{ font:400 clamp(2.25rem,5.5vw,3.4rem)/1 var(--font-display); letter-spacing:.01em; color:var(--crawl-yellow); text-shadow:var(--text-glow-hero); margin:0 0 24px; }
h2{ font:400 2rem/1.05 var(--font-outline); letter-spacing:.02em; color:var(--crawl-yellow); text-shadow:var(--text-glow); margin:0 0 16px; }
h3{ font:700 .8125rem/1.2 var(--font-body); letter-spacing:.18em; text-transform:uppercase; color:var(--crawl-yellow); margin:0 0 12px; }
p{ margin:0 0 16px; }
.lead{ font:500 1.15rem/1.6 var(--font-body); letter-spacing:.04em; color:var(--holo-cyan); }
.meta{ font:500 .8125rem/1.4 var(--font-body); letter-spacing:.06em; color:var(--steel); }

.container{ width:100%; max-width:1200px; margin:0 auto; padding:0 24px; }
.syrus-section{ padding:var(--section-pad) 0; position:relative; }
@media (max-width:991px){ :root{ --section-pad:64px; } }
@media (max-width:575px){ :root{ --section-pad:48px; } .container{ padding:0 16px; } }
```

---

## 4. Backgrounds & Atmosphere

- Page bg: flat `#04050A`. No photos. No image background on body.
- Nebula: three soft radial glows (in `body::before`, Section 3). Keep opacity at the measured values; do not brighten.
- Scanlines: `repeating-linear-gradient(90deg, rgba(4,5,10,.55) 0 2px, transparent 2px 4px)`.
- Starfield [spec]: tiny 1–2px dots in cream/cyan at random positions, opacity 0.2–0.8, slow twinkle. Canvas or CSS box-shadow stars. Keep behind content, `pointer-events:none`.
- Accent beam / divider [measured, 14 uses]:
  ```css
  .beam{ height:1px; border:0; background:linear-gradient(90deg, rgba(95,212,240,0), rgba(95,212,240,.95), rgba(255,251,224,0)); }
  ```
- Vertical rail: `linear-gradient(#5FD4F0, transparent)` or `linear-gradient(transparent, rgba(232,226,208,.5), transparent)`.
- Fade masks: `linear-gradient(transparent 0%, rgba(4,5,10,.55) 12%, rgba(4,5,10,.55) 100%)`.
- Glow orbs:
  - Yellow `radial-gradient(circle, #fff 0, rgba(255,240,140,.85) 25%, rgba(255,232,31,0) 70%)`
  - Cyan `radial-gradient(circle, #fff 0%, rgba(190,236,252,.75) 32%, rgba(95,212,240,.25) 58%, transparent 80%)`
- Metal (saber hilt, hardware) [measured]:
  - `linear-gradient(#5A5E66, #C9CCD2 45%, #6B6F78)`
  - `linear-gradient(#6B6F78, #E2E4E8 45%, #7B7F88)`

---

## 5. Elevation Rules

- Depth = glow. No `rgba(0,0,0,.x)` soft drop shadows.
- Cards: `--glow-frame` + inset 1px `--panel-border`.
- Hover: raise glow, never translate more than 2px.
- Active / current: yellow border `1.33px` + `--glow-yellow`.
- Focus-visible: `outline:2px solid var(--holo-cyan); outline-offset:3px;` [spec]

---

## 6. Motion System

Principles: slow ambient hum for glows, hard-cut flicker/blink for electronics, typewriter for terminal text, scroll-driven reveals for story sections. Easing `cubic-bezier(.2,.7,.2,1)` for reveals, `steps()` for typewriter. Durations: micro 150ms, reveal 600–900ms, ambient loops 2–6s.

Always include:
```css
@media (prefers-reduced-motion: reduce){ *{ animation:none !important; transition:none !important; scroll-behavior:auto !important; } }
```

Ready-to-use keyframes [spec, modeled on measured names]:

```css
@keyframes glow-in      { from{opacity:0; transform:translateY(12px); filter:blur(4px);} to{opacity:1; transform:none; filter:none;} }
@keyframes fade-in      { from{opacity:0} to{opacity:1} }
@keyframes blink        { 0%,49%{opacity:1} 50%,100%{opacity:0} }
@keyframes saberHum     { 0%,100%{box-shadow:var(--glow-saber); opacity:1} 50%{box-shadow:0 0 2px 1px #FFFBE0, 0 0 12px 3px rgba(255,232,31,.95), 0 0 40px 10px rgba(255,232,31,.3); opacity:.92} }
@keyframes numFlicker   { 0%,18%,22%,60%,64%,100%{opacity:1} 20%,62%{opacity:.35} }
@keyframes ringBlast    { from{transform:scale(.2); opacity:.9; border-color:var(--crawl-yellow);} to{transform:scale(2.4); opacity:0; border-color:transparent;} }
@keyframes hyperspaceStreak { from{transform:translateX(-120%) scaleX(.2); opacity:0;} 30%{opacity:1;} to{transform:translateX(120%) scaleX(1.6); opacity:0;} }
@keyframes scan         { from{transform:translateY(-100%)} to{transform:translateY(100%)} }
@keyframes ctaSweep     { from{transform:translateX(-120%) skewX(-20deg)} to{transform:translateX(220%) skewX(-20deg)} }
@keyframes edgeTrace    { from{stroke-dashoffset:var(--len,400)} to{stroke-dashoffset:0} }
@keyframes ping         { 0%{transform:scale(1); opacity:.8} 100%{transform:scale(2.2); opacity:0} }
@keyframes typewriter   { from{width:0} to{width:var(--chars,24ch)} }
```

Typewriter pattern (monospaced feel; use Oxanium, `white-space:nowrap`):
```css
.typed{ display:inline-block; overflow:hidden; white-space:nowrap; border-right:2px solid var(--crawl-yellow);
        width:var(--chars,24ch); animation:typewriter 2.4s steps(var(--steps,24)) 1 both, blink .8s step-end infinite; }
```

---

## 7. Iconography & Imagery [spec]

- Icons: thin line (1.5px stroke), square caps, cream or cyan. No filled colorful icons.
- Illustrations / mascots: Star Wars flavored line art or glowing vector (droid, saber, Yoda eye/arc). Single-color (yellow or cyan) with glow.
- Photos (gallery): `filter:saturate(.85) contrast(1.05)`, 1px cream hairline border, `--glow-frame`, no rounded corners, slight cyan tint on hover.
- Logos (sponsors): render in cream/steel monochrome (`filter:grayscale(1) brightness(1.2)`), full color not required. Hover: yellow glow.

---

## 8. Components (copy these)

### 8.1 Primary CTA
```css
.cta{
  position:relative; overflow:hidden; display:inline-flex; align-items:center; gap:8px;
  padding:14px 24px; background:var(--crawl-yellow); color:var(--void);
  font:700 .75rem/1 var(--font-body); letter-spacing:.14em; text-transform:uppercase;
  border:0; border-radius:var(--r-2); box-shadow:var(--glow-yellow); cursor:pointer;
  transition:box-shadow .25s, transform .25s, background .25s;
}
.cta::after{ content:""; position:absolute; inset:0; background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent); transform:translateX(-120%) skewX(-20deg); }
.cta:hover{ background:var(--yellow-soft); box-shadow:var(--glow-yellow-strong); transform:translateY(-1px); }
.cta:hover::after{ animation:ctaSweep .9s ease; }
.cta:active{ transform:none; }
.cta:focus-visible{ outline:2px solid var(--holo-cyan); outline-offset:3px; }
```

### 8.2 Ghost / display button
```css
.btn-ghost{
  padding:14px 28px; background:transparent; color:var(--crawl-yellow);
  font:400 1.35rem/1 var(--font-display); border:1.33px solid var(--crawl-yellow);
  border-radius:var(--r-2); cursor:pointer; transition:box-shadow .25s, background .25s;
}
.btn-ghost:hover{ background:rgba(255,232,31,.08); box-shadow:var(--glow-yellow); }
```

### 8.3 Card / panel
```css
.card{
  background:var(--panel); border:.67px solid var(--panel-border); border-radius:var(--r-1);
  box-shadow:var(--glow-frame), inset 0 0 0 1px var(--panel-border); padding:24px;
  transition:border-color .25s, box-shadow .25s;
}
.card:hover{ border-color:rgba(255,232,31,.6); box-shadow:var(--glow-frame), 0 0 18px rgba(255,232,31,.18); }
.card .meta{ margin-top:12px; }
```

### 8.4 HUD frame (translucent panel)
```css
.hud{ background:rgba(4,5,10,.72); border:.67px solid rgba(232,226,208,.30); box-shadow:var(--glow-frame); backdrop-filter:blur(6px); border-radius:var(--r-1); padding:24px; }
```

### 8.5 Header / nav
```css
.site-header{ position:fixed; inset:0 0 auto 0; z-index:50; background:rgba(4,5,10,.72); backdrop-filter:blur(8px); border-bottom:.67px solid rgba(232,226,208,.30); }
.site-header .bar{ display:flex; align-items:center; justify-content:space-between; height:64px; }
.site-nav a{ color:var(--cream); font:400 1rem/1 var(--font-body); padding:8px 12px; letter-spacing:.04em; }
.site-nav a:hover, .site-nav a.active{ color:var(--crawl-yellow); text-shadow:var(--text-glow-sm,0 0 14px rgba(255,232,31,.28)); }
.site-header::after{ content:""; position:absolute; left:0; right:0; bottom:-1px; height:1px; background:linear-gradient(90deg,transparent,var(--holo-cyan),transparent); }
```
Mobile (<768px): hamburger toggles full-screen overlay `rgba(4,5,10,.97)` with stacked links, Star Jedi 1.6rem, yellow.

### 8.6 Eyebrow + heading block (use for every section start)
```html
<h3>// 02 · PRIZE POOL</h3>
<h2>Claim Your Legacy</h2>
<hr class="beam">
```

### 8.7 Tag / chip
```css
.chip{ display:inline-block; padding:6px 10px; border:.67px solid rgba(232,226,208,.30); border-radius:var(--r-1); color:var(--cyan-hot,#BEECFC); font:600 .6875rem/1 var(--font-body); letter-spacing:.14em; text-transform:uppercase; }
.chip--active{ border-color:var(--crawl-yellow); color:var(--crawl-yellow); box-shadow:var(--glow-yellow); }
```

### 8.8 Form inputs
```css
.input{ width:100%; background:var(--panel); color:var(--cream); border:.67px solid var(--panel-border); border-radius:var(--r-1); padding:12px 14px; font:400 1rem var(--font-body); }
.input::placeholder{ color:var(--steel); }
.input:focus{ outline:none; border-color:var(--holo-cyan); box-shadow:var(--glow-cyan); }
label{ display:block; margin-bottom:8px; font:700 .75rem/1 var(--font-body); letter-spacing:.14em; text-transform:uppercase; color:var(--crawl-yellow); }
```

### 8.9 Accordion (FAQ)
```css
.faq-item{ border-bottom:2px solid rgba(232,226,208,.18); }
.faq-q{ width:100%; display:flex; justify-content:space-between; align-items:center; padding:20px 0; background:none; border:0; color:var(--cream); font:600 1.0625rem var(--font-body); text-align:left; cursor:pointer; }
.faq-q:hover{ color:var(--crawl-yellow); }
.faq-q .plus{ font-family:var(--font-display); color:var(--crawl-yellow); transition:transform .3s; }
.faq-item[open] .plus{ transform:rotate(45deg); }
.faq-a{ padding:0 0 20px; color:var(--cream-muted); animation:fade-in .4s ease; }
```
Use `<details class="faq-item"><summary class="faq-q">…</summary><div class="faq-a">…</div></details>`.

### 8.10 Timeline rail
- Vertical 2px line `linear-gradient(#5FD4F0, transparent)`.
- Nodes: 12px circles (`50%`), fill `--void`, border `1.33px solid cyan`, glow cyan. Active node: yellow border + `--glow-yellow`.
- Entry card appears with `glow-in` on scroll. Time label in h3 style.
- A side rail (`position:sticky`) lists times; current one highlights yellow.

### 8.11 Stat / numeral block (prize pool)
- Number in Star Jedi, `clamp(2.5rem,8vw,6rem)`, yellow, `--text-glow-lg` (`0 0 36px rgba(255,232,31,.28)`).
- On enter: `numFlicker` 0.8s then settle; a `ringBlast` ring (circle, 1.33px yellow border) expands behind it once.
- Plus / separator symbol with saber glow.
- Caption in h3 style below.

### 8.12 Saber line (progress / divider accent)
```css
.saber{ height:3px; width:100%; border-radius:var(--r-1); background:var(--yellow-hot); box-shadow:var(--glow-saber); animation:saberHum 3s ease-in-out infinite; }
.saber--cyan{ background:var(--cyan-hot); box-shadow:0 0 2px 1px #fff, 0 0 8px 2px rgba(95,212,240,.9), 0 0 30px 7px rgba(95,212,240,.3); }
```

### 8.13 Toast / alerts
Use stock colors from 2.1. Dark toasts (`#121212` bg), Oxanium text, `6px` radius is acceptable here only.

### 8.14 Footer
Top border `.67px solid rgba(232,226,208,.30)` + cyan beam. Panel bg `rgba(4,5,10,.97)`. 3–4 columns: brand (Star Jedi yellow wordmark), links (cream, hover yellow), contact (cyan), social icons (line, cream, hover yellow glow). Bottom row: `.meta` copyright, steel.

---

## 9. Page Blueprint (section order and treatment)

Use these ids in this order. Each section: `<section id="..." class="syrus-section">` + eyebrow/heading block (8.6) unless noted.

1. **`#intro`**: full-viewport hero. Opening-crawl feel: small cyan line "A long time ago…" style prologue fades in (`fade-in`), then h1 (event name, Star Jedi, yellow, hero glow), lead line in cyan, primary CTA + ghost CTA. Starfield background. Scroll hint line (thin vertical cyan beam + "SCROLL" micro label, pulsing). Optional pinned/scroll-driven crawl.
2. **`#sponsors`**: grid of monochrome logos in `.hud` frames, 2 cols mobile, 4–6 desktop. Tier labels as h3.
3. **`#prizepool`**: centered big numeral (8.11), hyperspace streaks passing behind, saber divider, prize breakdown as 3 cards.
4. **`#timeline`**: vertical rail timeline (8.10), sticky side rail nav.
5. **`#workshop`**: two-column: text left (lead + details), `.card` info stack right (date, venue, speaker) with chips.
6. **`#tracks`**: card grid (3 cols desktop, 1 mobile). Border-light trace on hover (SVG rect stroke-dash `edgeTrace`, or gradient border). Track number in Star Jedi, title in h3, description cream-muted.
7. **`#the-force`**: tall scroll-driven section (pinned). Story/CTA moment: large Star Jedi statement line, glowing eye/arc line art animating on scroll, final register CTA.
8. **`#faq-section`**: accordion (8.9), max-width 800px centered.
9. **`#gallery`**: masonry or 3-col grid of photos (Section 7 treatment), lightbox on click with `rgba(4,5,10,.97)` backdrop.
10. **`<footer>`**: 8.14.

Use `scroll-margin-top:80px` on sections so the fixed header does not cover headings.

---

## 10. Reveal-on-scroll pattern
```js
const io = new IntersectionObserver((entries)=>entries.forEach(e=>{ if(e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); } }), {threshold:.15});
document.querySelectorAll('[data-reveal]').forEach(el=>io.observe(el));
```
```css
[data-reveal]{ opacity:0; }
[data-reveal].in{ animation:glow-in .8s cubic-bezier(.2,.7,.2,1) forwards; }
```
Stagger children with `animation-delay: calc(var(--i) * 80ms)`.

---

## 11. Responsive Rules [spec]

| Width | Behavior |
|---|---|
| ≥1200 | 12-col grid, max 1200px container, 3–4 col card grids |
| 992–1199 | 3 cols → 2–3, section pad 64px |
| 768–991 | 2 cols, hamburger nav appears at <768 |
| 576–767 | 1–2 cols |
| <576 | 1 col, container pad 16px, h1 clamps to ~2.25rem, CTAs full width, scanlines off, reduce glow radii by ~40% for performance |

---

## 12. Accessibility [spec]

- Contrast: yellow/cyan/cream on `#04050A` all pass AA. Steel `#8B8F98` is fine for ≥13px meta, not for body.
- Never convey state with glow alone; add text or border change.
- Focus-visible ring on all interactive elements (cyan, 2px).
- `prefers-reduced-motion` block (Section 6) is mandatory.
- Decorative layers (stars, scanlines, beams) get `aria-hidden="true"` and `pointer-events:none`.
- Semantic HTML: one h1, sequential headings, `<nav>`, `<main>`, `<section>` with aria-labelledby.

---

## 13. Tone of Copy [spec]
Short, punchy, cinematic. Star Wars–flavored microcopy is welcome ("Register", "Join the Rebellion", "The Force Awaits", "Hyperspace Jump"). Labels uppercase. No emoji in UI. Numbers prefixed with `//` or `0X` for eyebrow ("// 03").

---

## 14. Hard Rules: Do / Don't

**DO**
- Background always `#04050A`.
- Yellow = titles + primary action. Cyan = lead copy + accents. Cream = reading text.
- Star Jedi display + Oxanium UI. Hollow for h2.
- Sharp 1–3px corners. Hairline borders. Uppercase tracked labels.
- Glow communicates hover, active, focus, current section.
- Keep images and logos desaturated or monochrome.

**DON'T**
- No light mode, no white surfaces, no gradients other than the ones listed.
- No rounded pill buttons, no large radii (>4px), no soft gray drop shadows.
- No Star Jedi in paragraphs. No bold Star Jedi (fake bold smears it).
- No extra accent hues (no purple, red, green) besides status toasts. Amber only as rare warning.
- No pure white `#FFF` text.
- No heavy animation on text blocks users must read.
- Don't use stock UI kits' default look (Bootstrap blue, Material shadows). Override everything.

---

## 15. Final Checklist (verify before delivering)

- [ ] `body` background is `#04050A`; nebula + (optional) scanlines present.
- [ ] Fonts load: Star Jedi, Star Jedi Hollow, Oxanium. If Star Jedi files missing, user was told.
- [ ] h1 yellow Star Jedi with hero glow; h2 yellow Star Jedi Hollow; h3 uppercase Oxanium `.18em`.
- [ ] Lead text cyan; body text cream; no pure white.
- [ ] Buttons: yellow fill + void text + `.14em` uppercase; glow on hover.
- [ ] Cards: `#12151B`, hairline `#2A2F39`, `--glow-frame`, radius ≤3px.
- [ ] Section ids and order match Section 9.
- [ ] Reveal-on-scroll + reduced-motion fallback implemented.
- [ ] Responsive at 360, 768, 1200, 1440px; no horizontal scroll.
- [ ] Focus states visible; semantic HTML.
- [ ] No colors, fonts, radii, or shadows used that aren't in this file.

---

## 16. Minimal HTML Skeleton

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EVENT NAME</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Oxanium:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="styles.css"> <!-- Section 3 + 6 + 8 -->
</head>
<body>
  <header class="site-header">
    <div class="container bar">
      <a class="brand" href="#intro" style="font-family:var(--font-display);color:var(--crawl-yellow);font-size:1.4rem">EVENT</a>
      <nav class="site-nav">
        <a href="#prizepool">Prizes</a><a href="#timeline">Timeline</a>
        <a href="#tracks">Tracks</a><a href="#faq-section">FAQ</a>
      </nav>
    </div>
  </header>
  <main>
    <section id="intro" class="syrus-section" style="min-height:100vh;display:flex;align-items:center">
      <div class="container">
        <p class="lead" data-reveal>A long time ago, in a campus far, far away…</p>
        <h1 data-reveal>EVENT NAME</h1>
        <p class="lead" data-reveal>One-line tagline here.</p>
        <a class="cta" href="#register">Register Now</a>
      </div>
    </section>
    <!-- #sponsors #prizepool #timeline #workshop #tracks #the-force #faq-section #gallery -->
  </main>
  <footer class="syrus-section"><div class="container meta">© YEAR ORGANIZER</div></footer>
</body>
</html>
```

---

## 17. Prompt to give the AI (copy-paste)

> Build a complete, responsive website for **[EVENT NAME]** using the attached `design.md` as the strict design system. Follow its tokens, fonts, components, section order and motion rules exactly. Use my content below for all copy. Output production-ready code (HTML/CSS/JS or React) with the Starter CSS from Section 3 as the base. If the Star Jedi font files are not available, use the specified fallback and tell me. Run the Section 15 checklist before replying.
>
> **My content:** [dates, venue, prize amounts, tracks, schedule, sponsors, FAQs, registration link, contact]

---

## 18. Provenance
Measured from `https://codecell-pp-cmpn.vesit.ves.ac.in/syrus` computed styles and stylesheets (colors, fonts, sizes, gradients, shadows, radii, keyframe names, section ids). Hover/focus states, spacing scale, responsive behavior, keyframe bodies, icon/image treatment and copy tone are **[spec]**: reasonable reconstructions in the same style, not read from the site.
