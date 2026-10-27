// Adapted from https://magicui.design/r/{blur-fade,number-ticker,border-beam}.json
// Magic UI (MIT), verified against the official registry on 2026-10-27.
// Local adaptations: Russian number formatting, reduced motion, semantic a11y count.
// Layout and colors follow the measured quiet-graphite reference.
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { motion, useInView, useMotionValue, useSpring } from "motion/react";

function subscribeMotionPreference(callback) {
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}
function useReducedMotion() {
  return useSyncExternalStore(
    subscribeMotionPreference,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => true,
  );
}

export function BlurFade({
  children,
  className,
  delay = 0,
  inView = false,
  ...props
}) {
  const ref = useRef(null);
  const visible = useInView(ref, { once: true, margin: "0px" });
  const reducedMotion = useReducedMotion();
  return (
    <motion.div
      ref={ref}
      className={className}
      data-magicui="blur-fade"
      initial={reducedMotion ? false : "hidden"}
      animate={reducedMotion || !inView || visible ? "visible" : "hidden"}
      variants={{
        hidden: { y: 0, opacity: 0, filter: "blur(4px)" },
        visible: { y: 0, opacity: 1, filter: "blur(0px)" },
      }}
      transition={{
        duration: reducedMotion ? 0 : 0.35,
        delay: reducedMotion ? 0 : delay,
        ease: "easeOut",
      }}
      {...props}
    >
      {children}
    </motion.div>
  );
}

const formatCount = (value) => new Intl.NumberFormat("ru-RU").format(value);

export function NumberTicker({ value, className = "" }) {
  const ref = useRef(null);
  const visible = useInView(ref, { once: true, margin: "0px" });
  const reducedMotion = useReducedMotion();
  const motionValue = useMotionValue(0);
  const springValue = useSpring(motionValue, { damping: 30, stiffness: 200 });
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    if (visible && !reducedMotion) motionValue.set(value);
  }, [visible, reducedMotion, motionValue, value]);
  useEffect(() => {
    if (reducedMotion) return;
    return springValue.on("change", (latest) => setDisplay(Math.round(latest)));
  }, [springValue, reducedMotion]);
  return (
    <span
      className={`inline-block tabular-nums ${className}`}
      data-magicui="number-ticker"
    >
      <span className="sr-only">{formatCount(value)}</span>
      <span ref={ref} aria-hidden="true">
        {formatCount(reducedMotion ? value : display)}
      </span>
    </span>
  );
}

export function BorderBeam() {
  const reducedMotion = useReducedMotion();
  if (reducedMotion) return null;
  return (
    <div
      aria-hidden="true"
      data-magicui="border-beam"
      className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit] border border-transparent mask-[linear-gradient(transparent,transparent),linear-gradient(currentColor,currentColor)] mask-intersect [mask-clip:padding-box,border-box]"
    >
      <motion.div
        className="absolute aspect-square bg-linear-to-l from-accent via-muted to-transparent"
        style={{ width: 120, offsetPath: "rect(0 auto auto 0 round 12px)" }}
        initial={{ offsetDistance: "0%", opacity: 0 }}
        animate={{ offsetDistance: "100%", opacity: [0, 0.8, 0.8, 0] }}
        transition={{ duration: 4, ease: "linear" }}
      />
    </div>
  );
}
