# Worklife interface

The application is a compact, dark desktop workspace for a personal job-search agent. Its first screen is organized around the person's next useful decision and real vacancies. Execution history is a secondary utility. The external MCP agent remains the main conversation surface; the UI does not pretend to send messages to a connected chat.

## Visual system

The 224 px material-like sidebar, blue-black content pane and company-colored cards form a desktop workspace inspired by native macOS navigation and readable productivity apps. The sidebar can collapse to a 64 px rail on an explicit click; this local preference persists. It never opens on hover. Vacancies are distinct cards with stable company monograms, subtle company tints, actual stages, pay, work format and evidence. Initials are not employer logos. Message cards prioritize sender, subject, body preview and actual unread state. Colors also distinguish résumé, market, schedule and setup surfaces; the utility journal remains compact.

The application uses the native macOS system-font stack (`-apple-system`, `BlinkMacSystemFont`, `system-ui`) with the bundled Golos family as a fallback. SF fonts are not embedded or downloaded. Golos and its SIL OFL license remain bundled for the public site's typography and fallback use. Page titles use 28/36 px, section and vacancy titles 16/24 px, body 14/22 px and secondary text 12–13 px. Semantic theme variables are scoped to `html.dark:has(.worklife-app)`, including portal dialogs.

Navigation icon colors distinguish the core destinations: overview blue, vacancies cyan, market amber, CV purple, employers teal and schedule rose. Primary actions are blue. Funnel chips use consistently labeled tones for application, reply, interview, offer and outcome. Text labels always accompany status colors. Content stays opaque and readable. Modest material depth separates the sidebar, working area, cards and dialogs. There are no decorative gradient headlines, blurred color blobs, fake metrics or marketing feature grids.

HeroUI supplies controls, dialogs, tables and disclosures, and Lucide supplies 16–18 px line icons. Keyboard focus is visible. Sidebars, headers and navigation do not animate into place. Magic UI's source components remain available for small content transitions and numeric values; reduced motion is respected.

## Information hierarchy

- **Start:** one short panel for the person's experience and job conditions, with real résumé navigation and the existing conditions dialog. No empty market metrics or fabricated activity.
- **Overview:** up to three real opportunities with their reasons and stage, followed by incoming messages and next actions. Actual conditions, résumé, market coverage and the next scheduled job form a secondary column when there is enough room. The latest three operations appear in a compact journal below.
- **Vacancies:** one title, cards/board switch, search and expandable composable filters. The filter button retains the active-filter count when collapsed. A recommendation stays with its vacancy rather than being repeated in a second list. The title opens the full evidence, CV and pipeline dialog.
- **Messages:** a dedicated sidebar destination with All / Unread / Unassigned views. Cards show sender, subject, time and preview. The reader opens the actual message first; explicit vacancy/read controls remain under a disclosure. The legacy `#search/inbox` route still opens the mail page. No guessed linkage or provider write is introduced by the redesign.
- **Market and résumés:** results and current documents take precedence over procedural explanation. Detailed methodology remains available through disclosure; important uncertainty remains visible.
- **Other sections:** the same typography, controls, open sections and dialog geometry apply to employers, schedules, experiments, resources and settings.

At 900 px the full compact sidebar remains visible; secondary overview content moves below results. Narrow devices retain the existing navigation dialog and larger input targets. Rows and dialogs wrap long Russian text and source references without horizontal page overflow.

## Data and behavior

All displayed counts, salaries, messages and outcomes come from the local API. Empty states remain empty. Synthetic visual-check data lives only in the isolated acceptance workspace, never in the person's real profile or shared employer database. UI changes preserve the existing tools, persistence, original résumé downloads, filters, pipeline updates and explicit message controls.

Current populated visual evidence and the isolated fictional demo are in `artifacts/macos-cards/`; the demo API alone sets `demo=true` to display its permanent label. The personal workspace is never seeded. Earlier design evidence remains in `artifacts/design-reset/`. Screenshots, not unit-test counts, are used to assess composition. Functional checks separately cover routes, filters, dialogs and navigation. The earlier raster-reference measurements in `artifacts/agency-build/` describe the previous layout and are not the acceptance target of this design.

## Public site

`Site.jsx` and its scoped `site.css` have their own presentation and release work. This app redesign does not edit the landing page or its installation workflow.

## Reference rationale

- [Apple Sidebars](https://developer.apple.com/design/human-interface-guidelines/sidebars): concise hierarchy, familiar symbols and an explicit hide/show control.
- [Apple Color](https://developer.apple.com/design/human-interface-guidelines/color): consistent semantic color with text/glyph alternatives.
- [Apple Materials](https://developer.apple.com/design/human-interface-guidelines/materials): separate navigation and content; avoid glass on every content card.
- [Apple Typography](https://developer.apple.com/design/human-interface-guidelines/typography): use system text, a coherent hierarchy and legible weights.
- [Codex public interface](https://openai.com/codex/): compact navigation and a distinct working pane. This is inspiration, not a claim of pixel identity with the installed app.
- [Sitepeel's critique](https://sitepeel.dev/guides/check-if-website-looks-ai-generated/) and [Superdesign's critique](https://superdesign.dev/blog/why-ai-design-looks-generic) informed the removal of generic copy, arbitrary effects and repetitive card layouts. These are editorial observations about generic design, not a reliable detector of AI authorship. Good usability conventions are retained.
