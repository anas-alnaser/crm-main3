import { motion } from "framer-motion";

export const pageMotion = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.2, ease: "easeOut" },
} as const;

export const modalMotion = {
  initial: { opacity: 0, scale: 0.98, y: 12 },
  animate: { opacity: 1, scale: 1, y: 0 },
  exit: { opacity: 0, scale: 0.98, y: 12 },
  transition: { duration: 0.18, ease: "easeOut" },
} as const;

export const drawerMotion = {
  initial: { opacity: 0, x: 28 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: 28 },
  transition: { duration: 0.2, ease: "easeOut" },
} as const;

export const MotionSection = motion.section;
export const MotionDiv = motion.div;
