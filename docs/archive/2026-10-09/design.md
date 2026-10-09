# 021 Trade — Visual Design Reference

> Source: https://021.trade/ · Inspected 7 October 2026.
> Purpose: a practical design reference for designers, developers, and AI coding tools, based on the public website’s rendered UI, computed styles, HTML, and delivered stylesheet.

## 1. Scope and evidence

This document describes the public website. It is not a specification of the authenticated Carbon trading terminal or Analytics product. Those destinations are linked from the site but their internal interfaces were not inspected.

### Evidence labels

- **Verified:** directly read from rendered DOM, computed CSS, HTML, or the delivered stylesheet.
- **Observed:** visible in browser screenshots; descriptions and approximate visual proportions.
- **Recommended:** an implementation decision for reproducing or adapting the appearance; not a claim about the original source.

### Pages reviewed

| Page | URL | Design coverage |
| --- | --- | --- |
| Homepage | https://021.trade/ | Hero, illustration system, philosophy, feature previews, brand statement, latency section, header/footer |
| Pricing | https://021.trade/pricing | Large price displays, both pricing tabs, dense charge grids, notes |
| Partnerships | https://021.trade/partner-with-us | Shared illustrated hero, three service cards, program comparison, proof cards, contact form |
| Features | https://021.trade/how-we-are-different | Two-column feature grid, icons, chips, informational callouts |
| Philosophy | https://021.trade/why-does-this-matter | Long-form article, section jumps, statistics, timeline, disclosures, interactive scorecard |
| Transparency | https://021.trade/transparency-report | Report disclosures, platform tabs, permissions grid, latency component |
| Support | https://021.trade/faq/ | Editorial header, search, topic sidebar, article cards, support panel |
| Blog | https://021.trade/blog/ | Editorial hero, illustration, horizontal topics, image-led article listing |
| Privacy | https://021.trade/privacy-policy | Legal document typography and shared marketing shell |

The global overflow menu and Company footer disclosure were opened. Both pricing categories were inspected. Form submission, account creation, authenticated screens, every article/legal route, and every report expansion were outside this visual review. Mobile behavior below is grounded in homepage responsive classes and stylesheet breakpoints, not a mobile screenshot audit.

## 2. Overall visual identity

**Observed:** The site feels calm, restrained, approachable, and service-oriented. White is the dominant surface. Muted gold identifies the brand and selected emphasis. Dark charcoal establishes readable text and occasional strong controls. Pale gray illustrations and fine borders let content remain the focus.

The characteristic ingredients are:

1. Large amounts of whitespace, especially above and around hero copy.
2. White or near-white surfaces with soft neutral borders.
3. Warm gold accents used sparingly for icons, headings, rules, and outlines.
4. Sans-serif typography with moderate size differences and clear weight hierarchy.
5. Rounded cards, nested panels, pills, and small line icons.
6. Friendly grayscale scenes rather than saturated stock photography.
7. Short, plain-language marketing statements and information-rich secondary pages.

The reviewed public pages use a light theme. Dark fills appear in buttons, pricing headers, social icons, and some embedded product illustrations. A full public dark-theme switching flow was not observed.

## 3. Color system

### Core palette

These hex values are present in source CSS and/or verified computed styles. Color roles reflect actual observed use; the site contains additional utility colors that should not all be treated as brand tokens.

| Token | Hex | Use and evidence |
| --- | --- | --- |
| `background` | `#FFFFFF` | Main homepage canvas and white controls; verified |
| `background-muted` | `#F0F0F0` | Marketing footer computed background; verified |
| `surface-subtle` | `#FAFAFA` | Zinc-50 feature/report surfaces; verified class/source |
| `surface-control` | `#F3F4F6` | Neutral utility surface for segmented controls and small labels; source + observed |
| `text-title` | `#141414` | Explicit `.text-title` source token; verified |
| `text-strong` | `#18181B` | Zinc-900, strong text and selected dark surfaces; source |
| `text-heading` | `#27272A` | Zinc-800 section titles; verified classes |
| `text-card` | `#3F3F46` | Zinc-700 card headings; source/computed correspondence |
| `text-body` | `#52525C` | Zinc-600 secondary content; source/computed correspondence |
| `text-muted` | `#71717B` | Zinc-500 labels and supporting copy; source/computed correspondence |
| `text-navigation` | `#364153` | Gray-700 navigation/footer text; source/computed correspondence |
| `text-supporting` | `#4A5565` | Gray-600 descriptive copy; source/computed correspondence |
| `border-neutral` | `#E5E7EB` | Homepage philosophy border uses gray-200; verified |
| `border-zinc` | `#E4E4E7` | Neutral cards, report dividers, chips; source/classes |
| `brand-gold` | `#A57D2D` | Explicit `.gold` and `.theme-golden`; hero emphasis, gold icons and rules; verified |
| `brand-gold-dark` | `#7F5606` | Explicit `.theme-dark-golden`; outlined CTA text/border computed RGB 127,86,6; verified |
| `brand-gold-light` | `#E5C97C` | Light-gold accents in dark embedded product UI; source/computed |
| `black` | `#000000` | Social icon backgrounds and scroll-to-top button; verified |

### Supporting warm palette

**Verified in stylesheet:** `#C7A35A`, `#D8BE86`, `#E2D3AF`, `#E8DFCC`, `#FFFDF9`, and several warm brown shades appear as utility colors. Use them for subtle borders, cream backgrounds, or supporting accents only where a corresponding component calls for them. Their presence in a bundled stylesheet alone does not prove every one appears on every page.

Gold opacity variants are also present: `#A57D2D` at 10%, 16%, 20%, 25%, and other opacities. White overlays at roughly 60–70% occur on feature preview cards and the secondary feature CTA. Soft gold/cream tinting should remain faint.

### Usage rules

- Keep most of the page white or near-white.
- Use dark text for titles and controls; gray text for descriptions and metadata.
- Apply gold to intentional emphasis, not every link or paragraph.
- Prefer borders and subtle surface differences over heavy shadows.
- The black pricing/table header is a local contrast device, not the page theme.
- Support email/telephone links use conventional blue in the FAQ template; do not force those into gold when matching that page.
- Gold gradients appear in decorative rules and treatments. Do not turn the entire interface into a metallic gradient.

## 4. Fonts and typography

### Two verified font systems

**Marketing pages:** computed font-family on homepage, pricing, transparency, and privacy content is:

```css
font-family: ui-sans-serif, system-ui, sans-serif,
  "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol",
  "Noto Color Emoji";
```

The marketing stylesheet also includes Inter variable `@font-face` declarations with weights 100–900 and `font-display: swap`. However, sampled marketing elements compute to the system stack. Do not claim the whole marketing site renders in Inter simply because Inter is bundled.

**FAQ/editorial pages:** sampled elements compute to `Inter` or `Inter, sans-serif`. This is a real distinction between the two website templates.

### Measured desktop typography

Measurements were taken in a browser viewport approximately 1363 × 936 CSS pixels. Some sizes are fluid and will change with viewport width.

| Element | Size | Weight | Line height | Notes |
| --- | --- | --- | --- | --- |
| Homepage hero H1 | 36px | 600 | 64px on H1 container | Split title; child lines and layout also influence appearance |
| Hero supporting paragraph | 16px | 400 | 24px | Centered, two lines at desktop |
| Header navigation | 14px | 400 | 20px | Compact rather than oversized |
| Hero sign-in CTA | 14px | 600 | 20px | Dark-gold outlined button |
| Homepage section H2 | 30px | 600 | 36px | Philosophy and latency headings |
| Philosophy card H3 | 30px | 500 | 37.5px | Lighter than section heading |
| Philosophy item text | 18px | 600 | 29.25px | Prominent benefit/problem rows |
| Philosophy eyebrow | 12px | 500 | 16px | Uppercase, spaced letters |
| Updates eyebrow | 11px | 500 | 16.5px | Small gold dot alongside label |
| Updates section title | 38.4px | 600 | 38.4px | Measured fluid size; not a global fixed H3 rule |
| Feature preview title | 18px | 600 | 24.75px | Compact card headline |
| Feature preview description | 14px | 400 | 22.75px | Gray, short preview |
| Brand statement | 18px | 600 / 400 | 29.25px | First paragraph stronger than second |
| Footer column title | 14px | 600 | 20px | Dense informational area |
| Footer address | 12px | 400 / 500 | 19.5px | First organization line slightly stronger |
| Footer accordion trigger | 14px | 500 | 20px | 12px vertical padding |
| Footer regulatory links | 12px | 400 | 16px | Wrapping line of links |
| Pricing explanatory H3 | 18px | 500 | — | Below large gold price numeral |
| Pricing tabs | 16px | 500 | — | Dark selected category |
| Transparency page title | 51.2px | — | 76.8px | Measured desktop size |
| Privacy page visual title | 51.2px | — | 76.8px | Rendered as paragraph in inspected DOM |
| Privacy section H2 | 20px | — | 28px | Compact legal hierarchy |
| Privacy paragraph | 14px | — | 22.75px, some 20px | Long-form readable body |
| FAQ page H1 | 30px | 700 | 34.5px | Inter |
| FAQ sidebar H3 | 20px | 700 | 23px | Inter |
| FAQ category controls | 15px | 600 | 25.6px | Inter |
| FAQ search input | 14px | 400 | normal | Inter |

### Typography principles

- Use sentence case for most titles; uppercase only for small category/eyebrow labels.
- Use weights 400, 500, and 600 across marketing; editorial headings also use 700.
- Preserve comfortable body leading: generally 1.5–1.65.
- Center hero and major section introductions; left-align card body content and articles.
- Avoid introducing a serif display face or monospaced primary font.
- Use semantic heading structure in a new implementation even when the source’s visual title is a paragraph.
- For new financial numeric interfaces, tabular numerals are a **recommended extension**, not a verified public-site rule.

## 5. Layout and spacing

### Verified layout foundation

The homepage HTML uses utility classes for responsive layout. Its philosophy content has `max-w-6xl`, the footer has `max-w-7xl`, and the latency explanatory paragraph measured 768px wide on desktop.

The homepage outer philosophy section uses `px-6`, `py-6`, `sm:py-12`, and `lg:px-24`. Under the normal 16px root/4px utility spacing scale, that corresponds to 24px base horizontal padding, 24px base vertical padding, 48px vertical padding from the small breakpoint, and 96px desktop horizontal padding.

Feature previews use `grid-cols-1`, `sm:grid-cols-2`, `lg:grid-cols-4`, and `gap-4`. The desktop screenshot shows four equal cards. Footer information uses one column, two from `md`, and four from `lg`, with `gap-8` increasing to `lg:gap-12`.

### Observed composition

- The header spans the viewport, with logo left and navigation right.
- The main hero occupies roughly a screen of height; its extensive blank upper region is intentional.
- Hero copy remains in a compact central area, surrounded by illustration elements near the lower and outer edges.
- Primary marketing card grids sit within a centered region around 1100–1200px wide.
- Philosophy is a two-column desktop comparison; features use four previews on homepage and two larger detail cards per row on the features page.
- Partnership content moves from three cards to a two-program comparison, then three proof cards and a narrower form.
- Long-form philosophy content uses a substantially narrower reading column than the card grids.
- FAQ uses a broad two-column layout: about one-quarter sidebar and three-quarters article results at the inspected desktop width.

### Recommended spacing tokens

Use a 4px base scale: `4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96`. Start with 16–24px card padding, 16–24px grid gaps, 48–80px section separation, and larger hero whitespace. These are practical reproduction defaults, not measured values for every original component.

## 6. Header and navigation

**Verified:** Homepage navigation uses a fixed top bar (`fixed top-0 w-full`) with transition duration 300ms. The marketing header contains the brand logo, Pricing, Partner with us, Support, and a small grid-style additional-menu control. Interior pages also show a pill-shaped sign-up/sign-in link.

Navigation links have 14px text, 8px vertical and 16px horizontal padding, and fully rounded corners. The observed hover treatment is a light gray capsule. The extra menu links to Blog, Carbon, and Analytics.

**Observed:** The logo is a compact gold vertical-bar/candlestick silhouette above widely spaced black brand lettering. The desktop header is visually light, with no heavy colored band.

For reproduction, retain the distinction between the homepage’s central hero CTA and the interior-page header CTA. Provide a compact accessible menu on small screens rather than forcing all desktop links into a narrow row.

The FAQ/blog header is separate: FAQs, Blog, Pricing, Search, and Sign Up. It should not be silently replaced with the marketing navigation when matching those pages.

## 7. Homepage section specifications

### 7.1 Illustrated hero

- Centered split headline: left half dark, right half gold, separated by a narrow vertical gold rule.
- Each half occupies two lines at desktop.
- Supporting text below, then a small white CTA with dark-gold outline and text.
- CTA verified: 1px border `#7F5606`, 8px radius, padding 8px 24px, 14px/600 text.
- Pale street scene surrounds the copy: left building with bell, tree, roadway, right building, and seated character.
- Illustration is intentionally low contrast; selected gold details reinforce brand recognition.
- Preserve generous negative space; do not enlarge the artwork until it competes with the heading.

### 7.2 Philosophy comparison

- Centered section heading with a short gold underline.
- Two large white rounded comparison cards with fine neutral borders.
- Left card presents things avoided, using gray/cross icon treatment.
- Right card presents service commitments, using gold/check icon treatment.
- Uppercase eyebrow, medium-weight card title, short underline, then generously spaced rows.
- Text links sit below the cards and include right arrows.
- Desktop measured card title 30px/500 and rows 18px/600.
- Homepage source includes different large-screen and smaller-screen arrangements with embedded product visuals. Do not infer mobile ordering by simply shrinking the desktop screenshot.

### 7.3 Feature previews

- Centered tiny eyebrow, large section heading, and muted one-line subtitle.
- Four equal desktop cards, each with a warm-tinted square icon tile and small Live status pill.
- Card title, short gray description, and subdued learn-more arrow link.
- Verified preview-link radius: 16px. White background is partially translucent.
- Warm fine border and very subtle depth; no heavy drop shadow.
- Centered pill-shaped all-features link beneath grid, with neutral border and 10px 20px padding.

### 7.4 Brand statement

- Wide rounded bordered panel with centered copy.
- First paragraph semibold, second regular.
- Thin, short decorative gold separator between the two.
- Inner paragraph measure is restrained with extra desktop horizontal padding.

### 7.5 Latency visualization

- Small gold eyebrow above a centered 30px section heading.
- System-to-exchange visual with central millisecond statistic and three processing checks.
- Supporting paragraph beneath in a constrained width.
- The inspected DOM showed an initial `0 ms` value. This should be treated as a captured runtime/initial state, not a verified performance measurement.
- The first full-page screenshot did not render the off-screen visualization completely. Do not reproduce blank space or missing lazy-loaded assets as intentional design.

## 8. Interior-page components

### 8.1 Pricing

Two large gold numerals with dark rupee symbols dominate the upper area. Each has an 18px explanatory caption. A centered two-tab segmented control sits below: pale neutral track, dark selected tab with light text, rounded corners and modest depth.

The charge matrix has a charcoal header, white body, thin gray grid lines, grouped column headings, and tiny pale Buy/Sell labels. The first column describes the charge; other columns organize trading segments. The second tab uses a simpler two-column matrix. Notes are left-aligned below.

Keep numerical alignment and readable spacing. For adaptation, make wide tables horizontally scrollable on narrow screens; this is a **recommended behavior**, not confirmed by a mobile interaction test. The screenshoted prices are current-page content, not permanent design tokens.

### 8.2 Feature detail page

Near-white canvas, centered heading/subtitle, and a two-by-two desktop card grid. Each card has a softly framed outer shell, white interior, gold line icon, small uppercase category, strong feature name, divider, gray description, small outlined chips, and a pale information strip with an info icon.

Card content should align consistently despite different description lengths. The visual vocabulary combines generous rounded shells with compact text and pill metadata.

### 8.3 Partnership page

The hero reuses the pale street scene but uses a single centered headline. Below it:

1. Three equal service cards with large gold outline icons and centered text.
2. Two broad program cards with upper-right ribbon labels, category eyebrow, large title, description, inset explanatory panel, and icon-led benefits.
3. Three proof cards with gold icons, bold metrics, muted copy, and full-width actions; dark-filled buttons coexist with a gold-outline action.
4. A centered narrow contact form.

The form has a rounded bordered white panel, a full-width name field, paired email/phone fields, full-width state selector, a two-column radio group, and a dark full-width submit button. Inputs have fine neutral borders, rounded corners, and faint shadow. Do not use this visual audit as evidence that validation or submission feedback was tested.

### 8.4 Transparency report

Very large centered title on a near-white canvas. Report rows appear as broad rounded white disclosures with gold document icon tiles, bold report label, tiny gold-outline duration badge, muted calendar/date row, and right-side chevron.

The permissions section uses a bordered panel, small gold brand eyebrow, strong section title, platform segmented tabs, and a dark-headed three-column information grid. The selected platform tab is white with subtle shadow, unlike pricing’s black selected category. Preserve this page-specific distinction.

### 8.5 Philosophy article and scorecard

Centered title and gold section-jump controls introduce a long reading column. The article uses dark headings, comfortable paragraph leading, statistics, a definition quote, chronological regulatory entries, and expandable subsections. Toward the bottom, grouped checkboxes and a score display create an interactive assessment.

This page demonstrates the brand’s approach to complex information: progressive disclosure, restrained borders, readable text, and concise emphasis. The underlying regulatory statements were not fact-checked in this design review.

### 8.6 Legal documents

The privacy page uses the marketing shell, a large visual title, 20px subsection headings, and 14px paragraphs/lists. It has a simple text-first presentation. Use a bounded reading area, natural paragraph spacing, and visibly distinct links. Keep long content left-aligned.

## 9. Support and editorial design

### FAQ

**Verified font:** Inter. Centered 30px bold title, centered bordered search field with magnifying-glass icon, then a broad sidebar/results layout.

- Sidebar: pale cool-neutral rounded panel, bold heading, many category rows with separators and chevrons.
- Results: category title and rule, then wide white outlined article cards.
- Cards: semibold article title, gray preview, thin divider, small date.
- Support panel: centered heading, copy, and blue contact links.
- Footer: simplified editorial variant with logo/social group, compact registration paragraph, app badges and QR.

### Blog index

- Large left-aligned introductory statement with grayscale laptop/beanbag character on the right.
- Horizontal topic strip with uppercase label, outlined rounded chips, black selected chip, and a subtle instruction to scroll.
- Image-led article listing. The first observed article uses a large image next to a prominent headline and metadata.
- Article previews use topic, heading, excerpt, publication date, and reading time hierarchy.

Do not infer every article-detail style from the index: individual blog articles were not exhaustively audited.

## 10. Footer

The marketing footer’s verified background is `#F0F0F0`, with 40px desktop vertical padding. Its first tier is a four-column desktop arrangement: logo/social icons, registered address, registration details, and app download badges/QR.

Below a horizontal divider are six full-width disclosures: company, account forms, disclaimer, client precautions, investor charter/grievance reports, and legal/regulatory information. Triggers use small dark text and chevrons. The opened Company disclosure reveals company resource links and founder links.

At the bottom, small regulatory links wrap with vertical separators, followed by centered chart-provider credit. A circular black scroll-to-top control with white icon is also present; measured diameter is 40px.

Social controls are 32px black rounded squares with white glyphs and 8px radius. Keep official store badges recognizable and undistorted. The QR sits on a small white rounded tile.

## 11. Shapes, borders, shadows, and icons

### Verified and observed geometry

| Component | Shape |
| --- | --- |
| Hero CTA | 8px radius, 1px dark-gold outline |
| Navigation capsules | Fully rounded |
| Additional-menu button | 8px radius |
| Feature preview | 16px radius |
| Responsive philosophy shells | Source uses 16px base / 24px from medium breakpoint |
| Secondary all-features CTA | Fully rounded, 1px neutral outline |
| Social buttons | 32px square, 8px radius |
| Back-to-top | 40px circle |
| Large content shells | Visually around 20–24px; exact values vary |

Many cards combine an outer border frame with an inset white surface. Shadows are faint and local, particularly on form fields, selected controls, and QR tiles. Do not add strong floating-card shadows everywhere.

Icons are thin, simple outlines: telescope, phone, anchor, compass, handshake, person-plus, candlestick chart, calendar, document, check/cross, arrows, and chevrons. Gold line icons often sit on cream or pale-gray rounded tiles. Use one consistent stroke system when adapting; the exact icon package was not verified.

## 12. Illustration and asset direction

### Verified homepage asset references

| Asset | Public path | Visual role |
| --- | --- | --- |
| Main logo | `/main-logo.png` | Gold bar/candlestick logo and wordmark |
| Road | `/road.svg` | Pale street-ground scene |
| Left house | `/left-house-with-bell.png` | Left-side building with small gold detail |
| Tree | `/tree.png` | Pale environmental illustration |
| Building | `/building.svg` | Right-side urban scene |
| Character | `/boy.webp` | Seated character in hero |
| Mobile lock screen | `/images/our-philosophy/Mobile_Lock_Screen.webp` | Embedded product example |
| Mobile callback | `/images/our-philosophy/Mobile_Request_Callback_Screen.webp` | Embedded product example |
| Callback | `/images/our-philosophy/Request_Callback_Screen.webp` | Product illustration |
| In-house stack | `/images/our-philosophy/Inhouse_Tech_Stack.webp` | Technology illustration |
| Charges screen | `/images/our-philosophy/Charges_Phone_Screen.webp` | Product illustration |
| Lock screen | `/images/our-philosophy/Lock-Screen.webp` | Product illustration |
| Nudges | `/images/our-philosophy/Nudges_Image.webp` | Concept illustration |
| Clutter | `/images/our-philosophy/Cluttered_Screen.webp` | Concept illustration |
| Fee transparency | `/images/our-philosophy/Fee_Transparency.webp` | Concept illustration |

Paths are relative to https://021.trade. Some rendered images use Next.js optimization URLs rather than the raw paths. These are reference locations, not a downloaded asset pack or a grant of reuse rights.

**Recommended for original assets:** use low-saturation gray illustration, simple city/character forms, white fading around the scene, and small gold accents. Keep typography out of generated imagery and render it as real text. Preserve SVG vector quality and raster aspect ratios.

## 13. Responsive behavior

### Verified stylesheet breakpoints

| Utility breakpoint | Minimum width |
| --- | --- |
| `sm` | 40rem / 640px |
| `md` | 48rem / 768px |
| `lg` | 64rem / 1024px |
| `xl` | 80rem / 1280px |
| `2xl` | 96rem / 1536px |

Pixel equivalents assume 16px root font size. Their presence confirms available breakpoints, not that every component uses all five.

### Verified homepage rules

- Hero H1: `text-2xl md:text-3xl lg:text-4xl` → 24px / 30px / 36px.
- Hero text alignment: centered initially, start-aligned at medium, centered again at large.
- Homepage section H2: 24px initially, 30px from large.
- Feature previews: one column → two at small → four at large.
- Footer: one column → two at medium → four at large.
- Desktop philosophy layout has a separate grid hidden below large; smaller-screen content has its own arrangement.
- Card shells increase corner radius and padding at medium in the source.

### Recommended implementation checks

At 375–430px, ensure no accidental horizontal page overflow, readable hero title, compact navigation, stacked cards, and intact form labels. At 768px, verify two-column content does not become cramped. At 1024–1440px, restore broad card grids and generous margins. Give data grids local horizontal scrolling where required. These checks are recommendations because mobile screenshots were not captured.

## 14. Motion and interaction

**Verified source:** HTML smooth scrolling is declared, Lenis-related rules are present, header color transitions use 300ms, and a hero entrance animation translates upward from 100px over 1.2s with `cubic-bezier(.33,1,.68,1)`. A signup entrance animation uses 0.4s with `cubic-bezier(.22,1,.36,1)`.

**Observed/tested:** Pricing tabs change the displayed charge grid; additional menu expands; Company footer disclosure expands. Topic categories, platform tabs, report rows, article disclosures, and scorecard controls are present. Not every control’s state transition was tested.

**Recommended:** keep movement subtle; use 150–300ms for hover/focus transitions, retain visible keyboard focus, and honor `prefers-reduced-motion`. Source contains reduced-motion-related media rules, but that does not establish that every animation has complete coverage.

Never copy a transient missing image, initial zero metric, stray template character, or delayed render as part of the intended design.

## 15. Accessible implementation guidance

These are recommendations for implementing the observed design, not an accessibility certification of the source website.

- Use meaningful heading order, labeled inputs, proper buttons and links.
- Preserve the observed skip-to-content pattern.
- Make icon-only menu and scroll controls accessible by name.
- Use tablist/tab/tabpanel semantics and selected-state announcements for segmented content; pricing already exposes these semantics.
- Associate disclosure buttons with expanded state and controlled regions.
- Do not rely on gold versus gray, checks versus crosses, or color alone to convey state.
- Ensure small muted text and gold labels have adequate contrast on their actual backgrounds.
- Use visible labels in new forms instead of relying only on placeholders.
- Provide error and success feedback when implementing submission; those states were not verified here.
- Treat wide charge grids as accessible tables in a new build even where the inspected source exposes generic DOM cells.

## 16. Starter CSS tokens

This is a **recommended normalized token layer** derived from verified colors and measurements. It is not a verbatim export of the website stylesheet.

```css
:root {
  --font-marketing: ui-sans-serif, system-ui, sans-serif;
  --font-editorial: "Inter", sans-serif;

  --background: #fff;
  --background-muted: #f0f0f0;
  --surface-subtle: #fafafa;
  --surface-control: #f3f4f6;
  --text-title: #141414;
  --text-heading: #27272a;
  --text-body: #52525c;
  --text-muted: #71717b;
  --border: #e5e7eb;
  --border-zinc: #e4e4e7;
  --gold: #a57d2d;
  --gold-dark: #7f5606;
  --gold-light: #e5c97c;
  --gold-wash: rgb(165 125 45 / 10%);

  --radius-control: 8px;
  --radius-card: 16px;
  --radius-shell: 24px;
  --radius-pill: 9999px;
  --content-wide: 1152px;
  --content-footer: 1280px;
  --content-reading: 768px;
}

body {
  margin: 0;
  background: var(--background);
  color: var(--text-title);
  font-family: var(--font-marketing);
  font-size: 16px;
  line-height: 1.5;
}

.editorial { font-family: var(--font-editorial); }
.card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 24px;
}
.button-gold-outline {
  background: #fff;
  border: 1px solid var(--gold-dark);
  border-radius: var(--radius-control);
  color: var(--gold-dark);
  padding: 8px 24px;
  font: 600 14px/20px var(--font-marketing);
}
.feature-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}
@media (min-width: 640px) {
  .feature-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (min-width: 1024px) {
  .feature-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
```

Load Inter explicitly only where needed; do not assume a declared font-face automatically applies to all content. Keep page-specific variants for pricing, feature detail cards, reports, and editorial components.

## 17. Guidance for AI-assisted implementation

Use this document as the visual reference and the product requirements as the authority for functionality.

- Build the shared marketing shell first: palette, system font, navigation, spacing, card borders, and footer.
- Match the intended page template: illustrated marketing page, dense pricing page, reading page, or Inter-based editorial page.
- Keep exact observed color tokens and typography where listed; treat approximate spacing as a starting point.
- Preserve light surfaces, grayscale illustrations, gold accents, and restrained depth.
- Keep content concise in cards and allow long-form pages a narrower reading measure.
- Do not invent a dark terminal theme, neon palette, giant display font, or heavy gradient background from this reference.
- Do not manufacture performance metrics or treat source marketing statements as verified application behavior.
- Separate reusable visual components from page content; prices, dates, and report periods are data.
- Verify desktop and mobile layouts, focus states, empty/loading/error states, and data-grid overflow before delivery.

## 18. Sources and limits

Primary sources are the page URLs in Section 1, direct browser screenshots/DOM/computed CSS from those pages, homepage HTML, and the delivered marketing stylesheet:

https://021.trade/_next/static/chunks/0efd29nsve_u9.css

The stylesheet filename is build-specific and may change. Measurements describe the site on the inspection date. This reference covers the recurring visual systems across the reviewed public pages; it does not claim an exhaustive audit of all routes, private products, mobile states, article details, or dynamic interaction outcomes.
