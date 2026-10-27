# Magic UI components

These local React components adapt the free [Magic UI](https://magicui.design) registry. Official source was retrieved through the Magic UI connector on 2026-10-27; animation keyframes were also checked against the JSON registry. They use the project's existing React and Motion dependencies. No package installation was needed.

| Local export | Official source |
| --- | --- |
| `Terminal`, `AnimatedSpan`, `TypingAnimation` | https://magicui.design/r/terminal.json |
| `TextAnimate` | https://magicui.design/r/text-animate.json |
| `AnimatedShinyText` | https://magicui.design/r/animated-shiny-text.json |
| `Marquee` | https://magicui.design/r/marquee.json |
| `ScrollProgress` | https://magicui.design/r/scroll-progress.json |
| `AnimatedBeam` | https://magicui.design/r/animated-beam.json |
| `OrbitingCircles` | https://magicui.design/r/orbiting-circles.json |
| `MagicCard` | https://magicui.design/r/magic-card.json |
| `WordRotate` | https://magicui.design/r/word-rotate.json |
| `LineShadowText` | https://magicui.design/r/line-shadow-text.json |
| `ShimmerLink` | https://magicui.design/r/shimmer-button.json |
| `BlurFade`, `BorderBeam`, `NumberTicker` in `src/magicui.jsx` | https://magicui.design/r/blur-fade.json · https://magicui.design/r/border-beam.json · https://magicui.design/r/number-ticker.json |

Local adaptations replace Tailwind utility strings with scoped CSS, remove TypeScript annotations, and use the site's fixed colors. `MagicCard` retains the pointer-following gradient variant without the Next.js theme provider. `ShimmerLink` uses an anchor for navigation. `TextAnimate` and the terminal retain complete text for assistive technology; `WordRotate` exposes a static description and reserves the widest word's width. Marquee copies are inert and hidden from screen readers. The system reduced-motion preference disables continuous animation and immediately shows terminal text.

Use a labeled demonstration when showing illustrative terminal output. Installation commands and their copy controls must use the actual supported command.

## License

MIT License

Copyright (c) Magic UI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
