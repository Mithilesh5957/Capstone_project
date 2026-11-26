import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

/* FACEATTEND UI primitives (R4 foundation, R5 hardened). Stable props,
 * sensible defaults, React 18 compatible. Components never fetch data.
 * FaModalFrame implements a full keyboard focus trap (Tab/Shift+Tab cycle,
 * Escape cancel, focus-in on open, focus restore on close, inert backdrop);
 * behavior is statically reviewed in R5 (no browser tooling to execute it). */

export function FaButton({
  variant = "primary",
  loading = false,
  children,
  ...rest
}) {
  const cls = `fa-btn fa-btn-${variant}`;
  return (
    <button className={cls} disabled={rest.disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading && <span className="fa-spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}

export function FaCard({ glass = false, className = "", children, ...rest }) {
  return (
    <div className={`${glass ? "fa-card-glass" : "fa-card"}${className ? ` ${className}` : ""}`} {...rest}>
      {children}
    </div>
  );
}

const TAG_CLASS = {
  ok: "fa-tag-ok",
  warn: "fa-tag-warn",
  err: "fa-tag-err",
  info: "fa-tag-info",
  neutral: "fa-tag-neutral",
};

/* Status is never color alone: dot shape + explicit text. */
export function FaStatusIndicator({ tone = "neutral", dot = true, children, ...rest }) {
  return (
    <span className={`fa-tag ${TAG_CLASS[tone] || TAG_CLASS.neutral}`} role="status" {...rest}>
      {dot && <span className="fa-dot" aria-hidden="true" />}
      {children}
    </span>
  );
}

export function FaFormField({ label, hint, error, errorId, children }) {
  const describedBy = [hint ? `${errorId}-hint` : null, error ? errorId : null]
    .filter(Boolean)
    .join(" ");
  return (
    <label className="fa-field">
      <span>{label}</span>
      {children(describedBy || undefined)}
      {hint && !error && (
        <span className="fa-hint" id={`${errorId}-hint`}>
          {hint}
        </span>
      )}
      {error && (
        <span className="fa-error" id={errorId} role="alert">
          {error}
        </span>
      )}
    </label>
  );
}

export function FaSectionHeader({ title, sub, actions, level = 2 }) {
  const Heading = level === 1 ? "h1" : level === 3 ? "h3" : "h2";
  return (
    <div className="fa-section-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
      <div>
        <Heading>{title}</Heading>
        {sub && <p>{sub}</p>}
      </div>
      {actions && <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>{actions}</div>}
    </div>
  );
}

/* Avatar chip with a deterministic hue derived from the record id, so the
 * same student always renders the same color without any network asset. */
export function FaAvatar({ id, name, size = 36 }) {
  const key = String(id ?? name ?? "?");
  let h = 0;
  for (let i = 0; i < key.length; i += 1) {
    h = (h * 31 + key.charCodeAt(i)) % 360;
  }
  const initials = (name || key || "?")
    .split(/[\s_-]+/)
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <span
      className="fa-avatar"
      aria-hidden="true"
      style={{
        width: size,
        height: size,
        fontSize: Math.max(11, Math.round(size * 0.36)),
        background: `linear-gradient(135deg, hsl(${h} 55% 42%), hsl(${(h + 40) % 360} 60% 32%))`,
      }}
    >
      {initials}
    </span>
  );
}

/* Transient feedback toast. Keeps role="status" semantics; the animation is
 * decorative and disabled under prefers-reduced-motion. */
export function FaToast({ tone = "neutral", children }) {
  const border = {
    ok: "var(--fa-ok)",
    warn: "var(--fa-warn)",
    err: "var(--fa-err)",
    info: "var(--fa-accent)",
    neutral: "var(--fa-border)",
  }[tone] || "var(--fa-border)";
  return (
    <div className="fa-toast" role="status" style={{ borderLeftColor: border }}>
      {children}
    </div>
  );
}

/* Loading placeholder: shimmer bar, no text (never asserted by tests). */
export function FaSkeleton({ width = "100%", height = 14 }) {
  return (
    <div className="fa-skeleton" aria-hidden="true" style={{ width, height }} />
  );
}
/* Accessible modal with a full keyboard focus trap. Contract (statically
 * reviewed in R5; no browser tooling to execute it): Escape cancels,
 * backdrop click cancels (non-destructive use only), focus moves into the
 * dialog on open, Tab/Shift+Tab cycle within the dialog, focus restores to
 * the opener on close, and background scrolling is locked while open. */
const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function FaModalFrame({ title, description, onCancel, actions, children, initialFocusRef }) {  const dialogRef = useRef(null);
  const openerRef = useRef(typeof document !== "undefined" ? document.activeElement : null);

  useEffect(() => {
    const root = dialogRef.current;
    const focusTarget = initialFocusRef?.current
      || (root && root.querySelector("[data-autofocus]"))
      || (root && root.querySelector("button"));
    if (focusTarget && focusTarget.focus) focusTarget.focus();
    const onKey = (e) => {
      if (e.key === "Escape" && onCancel) {
        e.stopPropagation();
        onCancel();
        return;
      }
      if (e.key !== "Tab" || !root) return;
      const items = Array.from(root.querySelectorAll(FOCUSABLE))
        .filter((el) => el.offsetParent !== null || el === document.activeElement);
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey, true);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const opener = openerRef.current;
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = prevOverflow;
      if (opener && opener.focus) {
        try {
          opener.focus();
        } catch {
          /* opener may be unmounted; nothing to restore */
        }
      }
    };
  }, [onCancel, initialFocusRef]);

  // Portal to document.body: a dialog must escape ancestor layout (margins,
  // transforms, overflow, z-index) — e.g. a parent `space-y-*` margin once
  // shifted this fixed backdrop by 16px, leaving a clickable strip.
  // Guarded for non-DOM environments; CRA renders client-side only.
  if (typeof document === "undefined" || !document.body) return null;
  return createPortal(
    <div
      className="fa-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && onCancel) onCancel();
      }}
    >
      <div className="fa-modal" role="dialog" aria-modal="true" aria-label={title} ref={dialogRef}>
        <h2>{title}</h2>
        {description && <p>{description}</p>}
        {children}
        {actions && <div className="fa-modal-actions">{actions}</div>}
      </div>
    </div>,
    document.body
  );
}
