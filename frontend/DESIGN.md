# Worklife interface

The approved visual reference is `design/references/2026-10-27-market-concepts/01-quiet-graphite.png`. Worklife uses its graphite background, slate surfaces, subdued blue accent, full-height sidebar, dominant activity journal and right-hand Market / Results / Next run rail. The reference is visual guidance; its demo records and market numbers never enter application state.

HeroUI 3 remains the component system. Typography uses its standard Heading / Paragraph variants and the native system font. Buttons, chips, tabs, tables, fields, accordions and dialogs keep native behavior. Icons come from one standard set, Lucide React; no custom SVG illustrations or component CSS are added.

The original color-only guard remains in `src/stock-theme.test.js`, extended only for the approved reference. Official theme variables `--radius` (0.25rem), `--field-radius` (0.5rem), `--surface-shadow`, `--overlay-shadow` and `--field-shadow` provide 12px component corners, 8px fields and thin semantic outlines. The standard Tailwind title token is 2.5rem and heading tracking is 0em to match the reference; font families and component typography variants remain native. The guard still rejects extra CSS files, component selectors, inline styles, arbitrary typography, literal JSX colors and hand-drawn SVG. A bounded set of layout, icon sizing and semantic color utilities is allowed.

The five everyday destinations stay visible: Overview, Market, Jobs, Employers and Schedule. Materials and Tools are native expandable disclosures; Settings is separate. Long navigation scrolls within the sidebar, with refresh time in the footer. Below 768px navigation opens in the native modal. Below 1280px the rail follows the journal so the columns remain readable.

Overview shows actual actions, timestamps, status and inspectable results. It keeps the journal visually dominant even when only two real calls exist. A saved resource opens from its actual related record. Missing records are not guessed. Empty, paused and scheduled states remain distinct. The optional embedded executor remains in Settings.

Market currently presents an honest “No comparable sample” state and counts of collected vacancies, employers, sources and vacancies with an explicit salary. It calculates no market median and does not describe selected vacancies as a representative market sample. Market methodology and backend tools are outside this design change.

The public page uses the same palette, shape tokens and line icons; its interactive synthetic examples remain explicitly labeled. Setup tabs and disclosures remain native HeroUI components.

Verification evidence for this pass is in `artifacts/reference-01-20261027-1936/`. It covers real sparse state, a separate offline populated fixture, desktop widths 1586 / 1440 / 1280, narrow fallback, all routes, result dialogs, forms, keyboard focus and computed contrast. Chrome rejected screenshot file writes under its configured roots; screenshots were inspected inline. Prior independent reports and scores remain unchanged. This implementation makes no independent fidelity score claim.
