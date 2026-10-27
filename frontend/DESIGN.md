# Worklife interface

The approved reference is `design/references/2026-10-27-market-concepts/01-quiet-graphite.png` (1586 × 992). The interface follows its measured geometry, restrained graphite surfaces, pale blue accent and ordinary line icons. Reference typography, spacing, corner radii and component styles are implemented explicitly in `src/styles.css`; the former color-only stock-component guard has been replaced because it prevented matching the approved reference.

At reference width, the sidebar is 246 px; main content starts at x=272; the journal is 898 px wide; the right rail starts at x=1190 and is 378 px wide. The title starts at (284,24) with 40 px / 48 px type. The three rail panels are Market, Results and Next run. Navigation and refresh remain stable during the initial API load. Main headings and page shells never animate into place. Only while a real profile needs setup, the existing onboarding panel leads the left column and the activity panel uses content height, keeping résumé and conditions actions visible on the first screen. The right rail and populated/reference layout stay in their original positions.

Typography uses self-hosted Golos Text, with normal 400, medium 500 and semibold 600 weights, on both the application and public site. It was chosen for its native Cyrillic text forms and screen-reading proportions. The original Google Fonts WOFF2 files, full SIL OFL 1.1 license and source hashes are in `src/fonts/`; the license is also copied into both published asset directories. Cyrillic and Latin are preloaded. `font-display: optional` prevents a late font swap on a slow connection; the Arial fallback has an adjusted x-height and explicit ascent/descent. Titles retain the reference line boxes, body copy remains normal weight, and financial values, counts and timestamps use tabular figures. Optical letter spacing and clearer empty-column labels improve scanability without changing the reference panel geometry.

HeroUI supplies accessible controls, modals, tables and disclosures; Lucide supplies icons. The five primary destinations remain visible. Materials expands to reveal résumés, strengths, repositories, sources, accounts, experiments and tactics. Narrow screens use a modal navigation menu and stacked content.

## Actual functionality

- Jobs: combined search, stage, location, source and remote filters; list and horizontally scrollable stage board; inspectable matching evidence and questions; CV comparison; saving a stage, note, next action and due date.
- Market: immutable snapshots and separate salary groups by currency, period and tax basis, descriptive distributions, source basis and explicit limitations. No synthetic salary default is used.
- Résumés: TXT, Markdown, PDF and DOCX upload through the local `/api/resume` endpoint, with variants and the existing document preview/download flow.
- Schedule: existing recurring tasks, pause/resume and history, plus interviews and offers with local persistence through the tools API.
- Overview: actual tool activity, market summary, local counts, the next scheduled task and grounded recommendations/setup prompts.

The main intelligence remains the user's connected MCP agent. The embedded model runtime remains optional in Settings. Empty profile, CV and vacancy states remain honest. Synthetic reference-comparison data exists only in an explicitly labeled artifact fixture; it is never written to the real workspace database.

## Magic UI provenance and motion

`src/magicui.jsx` adapts the free MIT-licensed Blur Fade, Number Ticker and Border Beam components from the official `https://magicui.design/r/<name>.json` registry. Registry sources for Blur Fade and Number Ticker were fetched and inspected on 2026-10-27. The existing `motion` dependency supplies the official motion primitives. This is component-source integration, not a renamed local UI library, and uses no paid components or API.

Local adaptations add Russian number formatting, an accessible final-value label and live `prefers-reduced-motion` support. Blur Fade is used for activity and vacancy records without translation of the application shell. Number Ticker displays real counts and reported medians. Border Beam remains available to the existing public site, but is not used in the quiet reference application panels. Reduced motion disables reveals and renders final numeric values immediately.

## Verification

`npm test` includes meaningful filter/state and missing/one-sided salary checks. The frontend build verifies the local and public asset paths before synchronizing generated files. Browser evidence, screenshots at 1586 / 1440 / 1280 / 390, and measured rectangles are in `artifacts/agency-build/frontend/`. The initial-load frame probe in `artifacts/initial-load-20261027/` remains available. An exact raster equality claim is not made: font rasterization, photographic texture in the source image and standard icon paths remain distinguishable.

## Public landing page

The public `Site.jsx` entry has a separate, scoped `site.css`. The landing uses a coastal photograph across the full first viewport, followed by problem → emotion → solution, an interactive search example, a six-principle manifesto, shared employer knowledge and setup. This presentation is separate from the application's quiet graphite workspace design. Synthetic demo vacancies are explicitly labeled.

`site-magicui.jsx` adapts the official MIT-licensed Shimmer Button as a navigation link. The existing Blur Fade and Border Beam supply entrance and example-frame motion. All animations respect reduced motion. Backgrounds are generated project-local JPEGs; exact prompts and generation provenance are recorded in `src/site-assets/README.md`.
