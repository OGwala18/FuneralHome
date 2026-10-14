import { type ReactNode, useId } from "react";
import { Label } from "@/components/ui/label";
import { AlertCircle } from "lucide-react";

interface FieldProps {
  label: string;
  /** Rendered with the id/aria wiring already applied. */
  children: (props: {
    id: string;
    "aria-invalid": boolean;
    "aria-describedby": string | undefined;
    "aria-required": boolean;
  }) => ReactNode;
  hint?: string;
  error?: string;
  required?: boolean;
  className?: string;
}

/**
 * One field, wired for screen readers.
 *
 * The label is always visible (never a placeholder standing in for a label —
 * placeholders vanish the moment someone types, which strands anyone who gets
 * interrupted mid-form). Errors are announced via role="alert" and linked with
 * aria-describedby so they are read out, not just seen.
 */
export function Field({ label, children, hint, error, required, className }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={className}>
      <Label htmlFor={id} className="mb-1.5 block text-sm font-medium">
        {label}
        {required && (
          <span className="ml-1 text-primary" aria-hidden="true">
            *
          </span>
        )}
        {!required && <span className="ml-2 text-xs font-normal text-muted-foreground">Optional</span>}
      </Label>

      {children({
        id,
        "aria-invalid": Boolean(error),
        "aria-describedby": describedBy,
        "aria-required": Boolean(required),
      })}

      {hint && !error && (
        <p id={hintId} className="mt-1.5 text-xs text-muted-foreground">
          {hint}
        </p>
      )}

      {error && (
        <p
          id={errorId}
          role="alert"
          className="mt-1.5 flex items-start gap-1.5 text-sm font-medium text-destructive"
        >
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}

interface StepIndicatorProps {
  current: 1 | 2;
  labels: [string, string];
}

/** Two-step progress. Conveys position by text as well as colour. */
export function StepIndicator({ current, labels }: StepIndicatorProps) {
  return (
    <nav aria-label="Registration progress" className="mb-8">
      <p className="sr-only">
        Step {current} of 2: {labels[current - 1]}
      </p>
      <ol className="flex items-center gap-3">
        {labels.map((label, index) => {
          const step = (index + 1) as 1 | 2;
          const isDone = step < current;
          const isCurrent = step === current;
          return (
            <li key={label} className="flex flex-1 items-center gap-3">
              <div className="flex flex-1 flex-col gap-2">
                <div
                  className={`h-1.5 rounded-full transition-colors duration-200 ${
                    isDone || isCurrent ? "bg-primary" : "bg-border"
                  }`}
                />
                <span
                  className={`text-xs font-medium ${
                    isCurrent ? "text-foreground" : "text-muted-foreground"
                  }`}
                >
                  <span aria-hidden="true">{step}. </span>
                  {label}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
