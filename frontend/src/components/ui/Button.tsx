import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";
import Icon, { type IconName } from "./Icon";

export type ButtonVariant = "primary" | "secondary" | "ghost";

const VARIANT: Record<ButtonVariant, string> = {
  primary: "nis-btn-primary",
  secondary: "nis-btn-secondary",
  ghost: "nis-btn-ghost",
};

/** Solid blue (primary) or white with blue text (secondary) NIS button. */
export function Button({
  variant = "secondary",
  icon,
  className = "",
  children,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; icon?: IconName; children: ReactNode }) {
  return (
    <button type={type} className={`${VARIANT[variant]} ${className}`} {...rest}>
      {icon && <Icon name={icon} size="1.2em" />}
      {children}
    </button>
  );
}

/** Router link that looks like a Button. */
export function ButtonLink({
  variant = "secondary",
  icon,
  className = "",
  children,
  ...rest
}: LinkProps & { variant?: ButtonVariant; icon?: IconName; children: ReactNode }) {
  return (
    <Link className={`${VARIANT[variant]} ${className}`} {...rest}>
      {icon && <Icon name={icon} size="1.2em" />}
      {children}
    </Link>
  );
}

/** Square icon-only button; `label` is required for screen readers. */
export function IconButton({
  icon,
  label,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { icon: IconName; label: string }) {
  return (
    <button type="button" aria-label={label} title={label} className={`nis-btn-icon ${className}`} {...rest}>
      <Icon name={icon} size="1.35em" />
    </button>
  );
}
