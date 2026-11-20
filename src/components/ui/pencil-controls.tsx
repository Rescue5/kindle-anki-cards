import * as React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { PencilFrame } from "@/components/sketch/sketch";
import { Input } from "@/components/ui/input";

/*
 * The controls of the "Кабинет" concept screens (docs/concept/*.dc.html, `kc-*`), built on the
 * existing pieces: lit and drawn buttons keep the `ui-button` states from night-reading.css, fields
 * wrap `Input`, frames and lines come from `components/sketch`. Only what the concept adds lives in
 * `design/cabinet.css`. Every control has hover, pressed, focus, disabled and loading states.
 */

type Look = "lit" | "drawn";

function Spinner() {
  return <Loader2 className="kc-spin" size={16} strokeWidth={1.8} aria-hidden="true" />;
}

// ---------- Buttons ----------

export type PencilButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  /** `lit` is the one primary action of a screen; `drawn` is outlined in pencil. */
  look?: Look;
  size?: "md" | "lg";
  /** A pending action: the button keeps its place, shows a spinner and ignores clicks. */
  loading?: boolean;
  /** A keyboard hint written inside the button, e.g. "1". */
  hint?: React.ReactNode;
};

export const PencilButton = React.forwardRef<HTMLButtonElement, PencilButtonProps>(
  ({ look = "drawn", size = "md", loading = false, hint, className, children, disabled, type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn("ui-button", look === "lit" ? "ui-button-lit" : "ui-button-drawn", "kc-btn", size === "lg" && "kc-btn-lg", className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      data-loading={loading ? "true" : undefined}
      {...props}
    >
      {look === "drawn" ? <PencilFrame /> : null}
      {loading ? <Spinner /> : null}
      {children}
      {hint ? <kbd>{hint}</kbd> : null}
    </button>
  ),
);
PencilButton.displayName = "PencilButton";

export type PencilChoiceProps = Omit<PencilButtonProps, "look" | "hint"> & {
  /** The choice that is currently made; announced as a pressed toggle. */
  pressed: boolean;
};

/** One of several answers (known / learn / skip): drawn when free, lit when chosen. */
export const PencilChoice = React.forwardRef<HTMLButtonElement, PencilChoiceProps>(
  ({ pressed, loading = false, className, children, disabled, type = "button", size = "md", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn("ui-button", "ui-button-drawn", "kc-btn", "kc-choice", size === "lg" && "kc-btn-lg", className)}
      aria-pressed={pressed}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      data-loading={loading ? "true" : undefined}
      {...props}
    >
      <PencilFrame />
      {loading ? <Spinner /> : null}
      {children}
    </button>
  ),
);
PencilChoice.displayName = "PencilChoice";

// ---------- Links ----------

type LinkCommon = {
  /** The light is on this link: it is the thing to do next. */
  lit?: boolean;
  loading?: boolean;
};
type PencilButtonLinkProps = LinkCommon & React.ButtonHTMLAttributes<HTMLButtonElement> & { href?: undefined };
type PencilAnchorLinkProps = LinkCommon & React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; disabled?: boolean };
export type PencilLinkProps = PencilButtonLinkProps | PencilAnchorLinkProps;

/** Text underlined in pencil. A button when it does something, an anchor when it has an `href`. */
export const PencilLink = React.forwardRef<HTMLElement, PencilLinkProps>(function PencilLink(props, ref) {
  const { lit = false, loading = false, className, children } = props;
  const classes = cn("kc-link", lit && "is-lit", className);
  const content = (
    <>
      {loading ? <Spinner /> : null}
      {children}
    </>
  );
  if (props.href !== undefined) {
    const { lit: _lit, loading: _loading, className: _class, children: _children, disabled, onClick, ...anchor } = props as PencilAnchorLinkProps;
    const inert = Boolean(disabled || loading);
    return (
      <a
        {...anchor}
        ref={ref as React.Ref<HTMLAnchorElement>}
        className={classes}
        aria-disabled={inert || undefined}
        aria-busy={loading || undefined}
        tabIndex={inert ? -1 : anchor.tabIndex}
        onClick={(event) => {
          if (inert) event.preventDefault();
          else onClick?.(event);
        }}
      >
        {content}
      </a>
    );
  }
  const { lit: _lit, loading: _loading, className: _class, children: _children, disabled, type = "button", ...button } = props as PencilButtonLinkProps;
  return (
    <button {...button} ref={ref as React.Ref<HTMLButtonElement>} type={type} className={classes} disabled={disabled || loading} aria-busy={loading || button["aria-busy"] || undefined}>
      {content}
    </button>
  );
});

// ---------- Radio: one of several examples ----------

export type PencilRadioOption<T extends string> = {
  value: T;
  /** What the option shows, e.g. a sentence with the word marked. */
  content: React.ReactNode;
  disabled?: boolean;
};

type PencilRadioGroupProps<T extends string> = {
  /** Names the group for screen readers. */
  label: string;
  value: T | null;
  options: PencilRadioOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
  /** A change is being saved: the group is dimmed and ignores input until it settles. */
  loading?: boolean;
  className?: string;
};

/** A group of round-dot options (`role="radiogroup"`); arrow keys move and choose, Home and End jump. */
export function PencilRadioGroup<T extends string>({ label, value, options, onChange, disabled = false, loading = false, className }: PencilRadioGroupProps<T>) {
  const refs = React.useRef<(HTMLButtonElement | null)[]>([]);
  const inert = disabled || loading;
  const enabled = options.map((option, index) => (option.disabled ? -1 : index)).filter((index) => index >= 0);
  const checkedIndex = options.findIndex((option) => option.value === value);
  const tabbable = checkedIndex >= 0 && !options[checkedIndex].disabled ? checkedIndex : enabled[0];

  function move(from: number, step: 1 | -1 | "first" | "last") {
    if (!enabled.length) return;
    const position = enabled.indexOf(from);
    const target =
      step === "first" ? enabled[0] : step === "last" ? enabled[enabled.length - 1] : enabled[(position + step + enabled.length) % enabled.length];
    refs.current[target]?.focus();
    onChange(options[target].value);
  }

  function onKeyDown(event: React.KeyboardEvent, index: number) {
    const keys: Record<string, 1 | -1 | "first" | "last"> = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1, Home: "first", End: "last" };
    const step = keys[event.key];
    if (step === undefined || inert) return;
    event.preventDefault();
    move(index, step);
  }

  return (
    <div role="radiogroup" aria-label={label} aria-busy={loading || undefined} aria-disabled={inert || undefined} className={cn("kc-radio-group", className)}>
      {options.map((option, index) => {
        const checked = option.value === value;
        return (
          <button
            key={option.value}
            ref={(node) => { refs.current[index] = node; }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={index === tabbable ? 0 : -1}
            className="kc-opt"
            disabled={inert || option.disabled}
            onClick={() => { if (!checked) onChange(option.value); }}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            <i aria-hidden="true" />
            <span>{option.content}</span>
          </button>
        );
      })}
    </div>
  );
}

// ---------- Text field ----------

export type PencilFieldProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> & {
  /** Always set: it names the input. Pass `hideLabel` when the screen already shows the caption. */
  label: string;
  hideLabel?: boolean;
  /** A quiet line under the field, e.g. what saving does. */
  hint?: string;
  /** What went wrong, in plain words; the line turns to the error colour and the text is announced. */
  error?: string;
  /** A save is in flight. */
  loading?: boolean;
  /** Fires on Enter and on leaving the field, only when the text changed since it got focus. */
  onCommit?: (value: string) => void;
};

/** A line of text written on a pencil rule; the rule warms on focus and reddens on error. */
export const PencilField = React.forwardRef<HTMLInputElement, PencilFieldProps>(
  ({ label, hideLabel = false, hint, error, loading = false, onCommit, className, id, onFocus, onBlur, onKeyDown, disabled, ...props }, ref) => {
    const generated = React.useId();
    const inputId = id ?? generated;
    const hintId = `${inputId}-hint`;
    const errorId = `${inputId}-error`;
    const focusValue = React.useRef("");

    function commit(value: string) {
      if (value === focusValue.current) return;
      focusValue.current = value;
      onCommit?.(value);
    }

    return (
      <div className={cn("kc-field", className)} data-invalid={error ? "true" : undefined} data-loading={loading ? "true" : undefined}>
        <label htmlFor={inputId} className={cn("kc-field-label", hideLabel && "sr-only")}>{label}</label>
        <div className="kc-field-control">
          <Input
            {...props}
            ref={ref}
            id={inputId}
            disabled={disabled}
            aria-invalid={error ? true : undefined}
            aria-busy={loading || undefined}
            aria-describedby={cn(error && errorId, hint && hintId) || undefined}
            onFocus={(event) => {
              focusValue.current = event.currentTarget.value;
              onFocus?.(event);
            }}
            onBlur={(event) => {
              commit(event.currentTarget.value);
              onBlur?.(event);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.nativeEvent.isComposing) commit(event.currentTarget.value);
              onKeyDown?.(event);
            }}
          />
          {loading ? <span className="kc-field-spinner"><Spinner /></span> : null}
        </div>
        {error ? <p id={errorId} role="alert" className="kc-field-error">{error}</p> : null}
        {hint ? <p id={hintId} className="kc-field-hint">{hint}</p> : null}
      </div>
    );
  },
);
PencilField.displayName = "PencilField";
