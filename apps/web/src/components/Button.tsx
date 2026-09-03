import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

/**
 * The one button treatment in the product.
 *
 * Primary actions are confident and quiet at the same time: a solid navy
 * rounded rectangle, never a pill, never a gradient. Secondary actions stay
 * visually quieter so a screen never competes with itself.
 */

type Variant = "primary" | "secondary" | "ghost";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-eaw font-medium transition-colors " +
  "disabled:cursor-not-allowed disabled:opacity-50";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-brand text-inverted hover:bg-brand-strong active:bg-brand-strong " +
    "disabled:hover:bg-brand",
  secondary:
    "border border-line-strong bg-surface text-ink hover:bg-surface-muted " +
    "active:bg-surface-muted",
  ghost: "text-brand hover:bg-brand-soft active:bg-brand-soft",
};

const SIZES = {
  md: "h-11 px-5 text-sm",
  lg: "h-13 px-6 text-base",
} as const;

interface ButtonStyleProps {
  variant?: Variant;
  size?: keyof typeof SIZES;
  className?: string;
}

function classes({ variant = "primary", size = "md", className = "" }: ButtonStyleProps) {
  return `${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${className}`.trim();
}

export function Button({
  variant,
  size,
  className,
  children,
  ...props
}: ButtonStyleProps & ComponentProps<"button">) {
  return (
    <button className={classes({ variant, size, className })} {...props}>
      {children}
    </button>
  );
}

export function ButtonLink({
  variant,
  size,
  className,
  href,
  children,
}: ButtonStyleProps & { href: string; children: ReactNode }) {
  return (
    <Link href={href} className={classes({ variant, size, className })}>
      {children}
    </Link>
  );
}
