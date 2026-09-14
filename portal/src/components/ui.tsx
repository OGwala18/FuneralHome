import type { ButtonHTMLAttributes, ReactNode } from "react";

/**
 * The four Figma component sets, as React. Button, Badge, Field and the notice
 * pattern. Keeping them here is what makes "the same button everywhere" true
 * rather than aspirational (Occam: one pattern per job).
 */

/* --------------------------------------------------------------- Button --- */

type ButtonVariant = "primary" | "secondary" | "ghost" | "selected" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  small?: boolean;
  block?: boolean;
  /** Shows a working state and disables the button, so it cannot fire twice. */
  loading?: boolean;
  loadingLabel?: string;
}

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: "btn-primary",
  secondary: "",
  ghost: "btn-ghost",
  selected: "btn-selected",
  danger: "btn-danger",
};

export function Button({
  variant = "secondary",
  small,
  block,
  loading,
  loadingLabel = "Working…",
  children,
  className = "",
  disabled,
  ...rest
}: ButtonProps) {
  const classes = [
    "btn",
    VARIANT_CLASS[variant],
    small ? "btn-small" : "",
    block ? "btn-block" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button className={classes} disabled={disabled || loading} {...rest}>
      {loading ? loadingLabel : children}
    </button>
  );
}

/* ---------------------------------------------------------------- Badge --- */

export type BadgeTone = "neutral" | "success" | "due" | "overdue";

/**
 * The label is required, not optional. Status must survive greyscale, so colour
 * never carries the meaning on its own.
 */
export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

/* ---------------------------------------------------------------- Field --- */

interface FieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  error?: string;
  type?: string;
  placeholder?: string;
  required?: boolean;
  autoComplete?: string;
  id?: string;
}

let fieldSeq = 0;

/**
 * Persistent label above the input, and a hint line that occupies its space
 * whether or not it has text, so an error appearing never shoves the rest of
 * the form down the page.
 */
export function Field({
  label,
  value,
  onChange,
  hint,
  error,
  type = "text",
  placeholder,
  required,
  autoComplete,
  id,
}: FieldProps) {
  const fieldId = id ?? `field-${++fieldSeq}`;
  const hintId = `${fieldId}-hint`;
  const message = error ?? hint ?? "";

  return (
    <div className={`field${error ? " field-error" : ""}`}>
      <label htmlFor={fieldId}>{label}</label>
      <input
        id={fieldId}
        type={type}
        value={value}
        placeholder={placeholder}
        required={required}
        autoComplete={autoComplete}
        aria-invalid={error ? true : undefined}
        aria-describedby={message ? hintId : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      <span className="field-hint" id={hintId} role={error ? "alert" : undefined}>
        {message}
      </span>
    </div>
  );
}

/* --------------------------------------------------------------- Notice --- */

export function Notice({
  tone = "neutral",
  title,
  detail,
  action,
}: {
  tone?: "neutral" | "success" | "warn" | "error";
  title: string;
  detail?: ReactNode;
  action?: ReactNode;
}) {
  const cls = tone === "neutral" ? "notice" : `notice notice-${tone}`;
  return (
    <div className={cls} role={tone === "error" ? "alert" : "status"}>
      <div className="stack-8">
        <span className="notice-title">{title}</span>
        {detail && <span className="t-small muted">{detail}</span>}
      </div>
      {action}
    </div>
  );
}

/* ----------------------------------------------------------------- Fact --- */

/** A labelled value. Grouping is by proximity, so there is no box around it. */
export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="fact">
      <span className="t-micro">{label}</span>
      <span>{children}</span>
    </div>
  );
}

/* -------------------------------------------------------------- Loading --- */

/**
 * Skeletons rather than a spinner. The shape of the answer is already known, so
 * nothing jumps when the data lands (Doherty: keep the wait legible).
 */
export function Skeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className="skeleton skeleton-line"
          style={{ width: `${100 - (i % 3) * 12}%` }}
        />
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- Empty --- */

/** Empty states teach the screen rather than announcing that it is empty. */
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-title">{title}</div>
      {children && <div className="t-small muted">{children}</div>}
    </div>
  );
}
