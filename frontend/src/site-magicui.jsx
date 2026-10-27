// Adapted from the official Magic UI registry (MIT). See ../MAGICUI.md.
// Copyright (c) Magic UI. Registry source inspected 2026-10-27.
// Local adaptations: plain CSS, semantic elements, reduced motion, static a11y text.
import { Children, createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useMotionTemplate, useMotionValue, useReducedMotion, useScroll } from "motion/react";
import "./site-magicui.css";

const classes = (...values) => values.filter(Boolean).join(" ");
const motionElements = { article: motion.article, div: motion.div, h1: motion.h1, h2: motion.h2, h3: motion.h3, h4: motion.h4, p: motion.p, section: motion.section, span: motion.span };

// https://magicui.design/r/shimmer-button.json
export function ShimmerLink({ children, href, className, ...props }) {
  return <a className={classes("wl-shimmer", className)} href={href} data-magicui="shimmer-button" {...props}>
    <span className="wl-shimmer-spark-container" aria-hidden="true"><span className="wl-shimmer-slide"><span className="wl-shimmer-spin" /></span></span>
    <span className="wl-shimmer-content">{children}</span>
    <span className="wl-shimmer-highlight" aria-hidden="true" />
    <span className="wl-shimmer-backdrop" aria-hidden="true" />
  </a>;
}

// https://magicui.design/r/terminal.json
const SequenceContext = createContext(null);
const ItemIndexContext = createContext(null);

export function Terminal({ children, className, sequence = true, startOnView = true, title = "worklife", label, actions, ...props }) {
  const containerRef = useRef(null);
  const isInView = useInView(containerRef, { amount: 0.25, once: true });
  const reducedMotion = useReducedMotion();
  const [activeIndex, setActiveIndex] = useState(0);
  const completeItem = useCallback((index) => setActiveIndex(current => index === current ? current + 1 : current), []);
  const sequenceStarted = reducedMotion || !startOnView || isInView;
  const context = useMemo(() => sequence ? { completeItem, activeIndex, sequenceStarted } : null, [sequence, completeItem, activeIndex, sequenceStarted]);
  const rows = sequence ? Children.toArray(children).map((child, index) => <ItemIndexContext.Provider value={index} key={index}>{child}</ItemIndexContext.Provider>) : children;
  return <SequenceContext.Provider value={context}>
    <div ref={containerRef} className={classes("mui-terminal", className)} data-magicui="terminal" {...props}>
      <div className="mui-terminal-bar">
        <span className="mui-terminal-dots" aria-hidden="true"><i /><i /><i /></span>
        <span className="mui-terminal-title">{title}</span>
        {label && <span className="mui-terminal-label">{label}</span>}
        {actions && <div className="mui-terminal-actions">{actions}</div>}
      </div>
      <pre className="mui-terminal-body"><code>{rows}</code></pre>
    </div>
  </SequenceContext.Provider>;
}

export function AnimatedSpan({ children, delay = 0, className, startOnView = false, ...props }) {
  const ref = useRef(null);
  const isInView = useInView(ref, { amount: 0.25, once: true });
  const sequence = useContext(SequenceContext);
  const index = useContext(ItemIndexContext);
  const reducedMotion = useReducedMotion();
  const visible = reducedMotion || (sequence ? sequence.sequenceStarted && sequence.activeIndex >= index : !startOnView || isInView);
  const completeItem = sequence?.completeItem;
  useEffect(() => {
    if (!visible || !completeItem || index === null) return;
    const timer = setTimeout(() => completeItem(index), reducedMotion ? 0 : 300);
    return () => clearTimeout(timer);
  }, [visible, completeItem, index, reducedMotion]);
  return <span ref={ref} className={classes("mui-terminal-line", className)} data-magicui="animated-span" {...props}>
    <span className="mui-sr-only">{children}</span>
    <motion.span aria-hidden="true" className="mui-terminal-line-visual" initial={reducedMotion ? false : { opacity: 0, y: -5 }} animate={visible ? { opacity: 1, y: 0 } : { opacity: 0, y: -5 }} transition={{ duration: reducedMotion ? 0 : 0.3, delay: sequence || reducedMotion ? 0 : delay / 1000 }}>{children}</motion.span>
  </span>;
}

export function TypingAnimation({ children, duration = 40, delay = 0, className, as = "span", startOnView = true, ...props }) {
  const text = String(children ?? "");
  const ref = useRef(null);
  const isInView = useInView(ref, { amount: 0.25, once: true });
  const sequence = useContext(SequenceContext);
  const index = useContext(ItemIndexContext);
  const reducedMotion = useReducedMotion();
  const [displayedText, setDisplayedText] = useState("");
  const started = sequence ? sequence.sequenceStarted && sequence.activeIndex >= index : !startOnView || isInView;
  const completeItem = sequence?.completeItem;
  const Component = as;
  useEffect(() => {
    if (!started) return;
    let interval;
    const timer = setTimeout(() => {
      if (reducedMotion || duration <= 0 || !text.length) {
        setDisplayedText(text);
        if (index !== null) completeItem?.(index);
        return;
      }
      let count = 0;
      interval = setInterval(() => {
        count += 1;
        setDisplayedText(text.slice(0, count));
        if (count >= text.length) {
          clearInterval(interval);
          if (index !== null) completeItem?.(index);
        }
      }, duration);
    }, reducedMotion ? 0 : delay);
    return () => { clearTimeout(timer); clearInterval(interval); };
  }, [started, text, duration, delay, reducedMotion, completeItem, index]);
  return <Component ref={ref} className={classes("mui-typing", className)} data-magicui="typing-animation" {...props}>
    <span className="mui-sr-only">{text}</span><span aria-hidden="true">{reducedMotion ? text : displayedText}<span className="mui-typing-caret" data-complete={displayedText === text} /></span>
  </Component>;
}

// https://magicui.design/r/text-animate.json
const textHidden = {
  fadeIn: { opacity: 0, y: 20 }, blurIn: { opacity: 0, filter: "blur(10px)" },
  blurInUp: { opacity: 0, filter: "blur(10px)", y: 20 }, blurInDown: { opacity: 0, filter: "blur(10px)", y: -20 },
  slideUp: { opacity: 0, y: 20 }, slideDown: { opacity: 0, y: -20 },
  slideLeft: { opacity: 0, x: 20 }, slideRight: { opacity: 0, x: -20 },
  scaleUp: { opacity: 0, scale: 0.5 }, scaleDown: { opacity: 0, scale: 1.5 },
};
export function TextAnimate({ children, className, segmentClassName, as = "p", by = "word", animation = "fadeIn", delay = 0, duration = 0.5, startOnView = true, once = true, ...props }) {
  const reducedMotion = useReducedMotion();
  const text = String(children ?? "");
  const MotionComponent = motionElements[as] || motion.p;
  const segments = by === "word" ? text.split(/(\s+)/) : by === "character" ? Array.from(text) : by === "line" ? text.split("\n") : [text];
  return <MotionComponent className={classes("mui-text-animate", className)} data-magicui="text-animate" initial={reducedMotion ? false : "hidden"} animate={reducedMotion || !startOnView ? "show" : undefined} whileInView={startOnView ? "show" : undefined} viewport={{ once, amount: 0.25 }} variants={{ hidden: {}, show: { transition: { delayChildren: reducedMotion ? 0 : delay, staggerChildren: reducedMotion ? 0 : duration / Math.max(segments.length, 1) } } }} {...props}>
    <span className="mui-sr-only">{text}</span>
    {segments.map((segment, index) => <motion.span key={index} aria-hidden="true" className={classes(by === "line" ? "mui-text-line" : "mui-text-segment", segmentClassName)} variants={{ hidden: textHidden[animation] || textHidden.fadeIn, show: { opacity: 1, x: 0, y: 0, scale: 1, filter: "blur(0px)", transition: { duration: reducedMotion ? 0 : 0.35 } } }}>{segment}</motion.span>)}
  </MotionComponent>;
}

// https://magicui.design/r/animated-shiny-text.json
export function AnimatedShinyText({ children, className, shimmerWidth = 100, style, ...props }) {
  return <span className={classes("mui-shiny-text", className)} style={{ "--shiny-width": `${shimmerWidth}px`, ...style }} data-magicui="animated-shiny-text" {...props}>{children}</span>;
}

// https://magicui.design/r/marquee.json
export function Marquee({ className, reverse = false, pauseOnHover = true, children, vertical = false, repeat = 3, duration = 36, style, ...props }) {
  return <div className={classes("mui-marquee", vertical && "mui-marquee-vertical", pauseOnHover && "mui-marquee-pausable", className)} style={{ "--marquee-duration": `${duration}s`, ...style }} data-magicui="marquee" {...props}>
    {Array.from({ length: repeat }, (_, index) => <div key={index} className="mui-marquee-track" aria-hidden={index > 0 ? true : undefined} inert={index > 0 ? true : undefined} style={{ animationDirection: reverse ? "reverse" : undefined }}>{children}</div>)}
  </div>;
}

// https://magicui.design/r/scroll-progress.json
export function ScrollProgress({ className, style, ...props }) {
  const { scrollYProgress } = useScroll();
  return <motion.div aria-hidden="true" className={classes("mui-scroll-progress", className)} style={{ scaleX: scrollYProgress, ...style }} data-magicui="scroll-progress" {...props} />;
}

// https://magicui.design/r/animated-beam.json
export function AnimatedBeam({ className, containerRef, fromRef, toRef, curvature = 0, reverse = false, duration = 5, delay = 0, pathColor = "#9bacb7", pathWidth = 1, pathOpacity = 0.25, gradientStartColor = "#8fb5ce", gradientStopColor = "#edf5fa", repeat = Infinity, repeatDelay = 0, startXOffset = 0, startYOffset = 0, endXOffset = 0, endYOffset = 0 }) {
  const id = useId();
  const reducedMotion = useReducedMotion();
  const [geometry, setGeometry] = useState({ path: "", width: 0, height: 0 });
  useEffect(() => {
    const container = containerRef.current, from = fromRef.current, to = toRef.current;
    if (!container || !from || !to) return;
    const update = () => {
      const base = container.getBoundingClientRect(), a = from.getBoundingClientRect(), b = to.getBoundingClientRect();
      const x1 = a.left - base.left + a.width / 2 + startXOffset, y1 = a.top - base.top + a.height / 2 + startYOffset;
      const x2 = b.left - base.left + b.width / 2 + endXOffset, y2 = b.top - base.top + b.height / 2 + endYOffset;
      setGeometry({ width: base.width, height: base.height, path: `M ${x1},${y1} Q ${(x1 + x2) / 2},${y1 - curvature} ${x2},${y2}` });
    };
    const observer = new ResizeObserver(update);
    [container, from, to].forEach(element => observer.observe(element));
    update();
    return () => observer.disconnect();
  }, [containerRef, fromRef, toRef, curvature, startXOffset, startYOffset, endXOffset, endYOffset]);
  if (!geometry.width || !geometry.height) return null;
  return <svg aria-hidden="true" fill="none" className={classes("mui-animated-beam", className)} width={geometry.width} height={geometry.height} viewBox={`0 0 ${geometry.width} ${geometry.height}`} data-magicui="animated-beam">
    <path d={geometry.path} stroke={pathColor} strokeWidth={pathWidth} strokeOpacity={pathOpacity} strokeLinecap="round" />
    {!reducedMotion && <><path d={geometry.path} strokeWidth={pathWidth} stroke={`url(#${id})`} strokeLinecap="round" /><defs><motion.linearGradient id={id} gradientUnits="userSpaceOnUse" initial={{ x1: "0%", x2: "0%", y1: "0%", y2: "0%" }} animate={{ x1: reverse ? ["90%", "-10%"] : ["10%", "110%"], x2: reverse ? ["100%", "0%"] : ["0%", "100%"], y1: ["0%", "0%"], y2: ["0%", "0%"] }} transition={{ delay, duration, ease: [0.16, 1, 0.3, 1], repeat, repeatDelay }}><stop stopColor={gradientStartColor} stopOpacity="0" /><stop stopColor={gradientStartColor} /><stop offset="32.5%" stopColor={gradientStopColor} /><stop offset="100%" stopColor={gradientStopColor} stopOpacity="0" /></motion.linearGradient></defs></>}
  </svg>;
}

// https://magicui.design/r/orbiting-circles.json
export function OrbitingCircles({ className, children, reverse = false, duration = 30, delay = 0, radius = 120, path = true, iconSize = 42, speed = 1, style, ...props }) {
  const items = Children.toArray(children);
  return <>
    {path && <svg className="mui-orbit-path" aria-hidden="true"><circle cx="50%" cy="50%" r={radius} fill="none" /></svg>}
    {items.map((child, index) => <div key={index} className={classes("mui-orbit", className)} style={{ "--orbit-duration": `${duration / speed}s`, "--orbit-radius": `${radius}px`, "--orbit-angle": `${360 / items.length * index}deg`, "--orbit-size": `${iconSize}px`, animationDirection: reverse ? "reverse" : undefined, animationDelay: `${delay}s`, ...style }} data-magicui="orbiting-circles" {...props}>{child}</div>)}
  </>;
}

// https://magicui.design/r/magic-card.json — gradient variant, fixed site theme.
export function MagicCard({ children, className, contentClassName, gradientSize = 200, gradientColor = "#96bcd220", gradientOpacity = 0.8, gradientFrom = "#9cc7df", gradientTo = "#526d86", as: Component = "div", style, ...props }) {
  const reducedMotion = useReducedMotion();
  const mouseX = useMotionValue(-gradientSize), mouseY = useMotionValue(-gradientSize);
  const border = useMotionTemplate`linear-gradient(var(--magic-card-bg, #111a23) 0 0) padding-box, radial-gradient(${gradientSize}px circle at ${mouseX}px ${mouseY}px, ${gradientFrom}, ${gradientTo}, var(--magic-card-border, #ffffff18) 100%) border-box`;
  const spotlight = useMotionTemplate`radial-gradient(${gradientSize}px circle at ${mouseX}px ${mouseY}px, ${gradientColor}, transparent 100%)`;
  return <Component className={classes("mui-magic-card", className)} style={style} data-magicui="magic-card" onPointerMove={event => { if (reducedMotion || event.pointerType === "touch") return; const rect = event.currentTarget.getBoundingClientRect(); mouseX.set(event.clientX - rect.left); mouseY.set(event.clientY - rect.top); }} onPointerLeave={() => { mouseX.set(-gradientSize); mouseY.set(-gradientSize); }} {...props}>
    <motion.div className="mui-magic-card-border" aria-hidden="true" style={{ background: border }} />
    <motion.div className="mui-magic-card-glow" aria-hidden="true" style={{ background: spotlight, opacity: reducedMotion ? 0 : gradientOpacity }} />
    <div className={classes("mui-magic-card-content", contentClassName)}>{children}</div>
  </Component>;
}

// https://magicui.design/r/word-rotate.json
export function WordRotate({ words, duration = 2800, className, accessibleLabel, motionProps, ...props }) {
  const reducedMotion = useReducedMotion();
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (reducedMotion || words.length < 2) return;
    const interval = setInterval(() => setIndex(current => (current + 1) % words.length), duration);
    return () => clearInterval(interval);
  }, [duration, words.length, reducedMotion]);
  return <span className={classes("mui-word-rotate", className)} data-magicui="word-rotate" {...props}>
    <span className="mui-sr-only">{accessibleLabel || words.join(", ")}</span>
    <span className="mui-word-rotate-stage" aria-hidden="true"><span className="mui-word-rotate-sizer">{words.map(word => <span key={word}>{word}</span>)}</span><AnimatePresence mode="wait" initial={false}><motion.span className="mui-word-rotate-word" key={reducedMotion ? words[0] : words[index % words.length]} initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }} transition={{ duration: reducedMotion ? 0 : 0.25, ease: "easeOut" }} {...motionProps}>{reducedMotion ? words[0] : words[index % words.length]}</motion.span></AnimatePresence></span>
  </span>;
}

// https://magicui.design/r/line-shadow-text.json
export function LineShadowText({ children, shadowColor = "#9eb7c7", className, as: Component = "span", style, ...props }) {
  return <Component className={classes("mui-line-shadow", className)} style={{ "--shadow-color": shadowColor, ...style }} data-text={children} data-magicui="line-shadow-text" {...props}>{children}</Component>;
}
