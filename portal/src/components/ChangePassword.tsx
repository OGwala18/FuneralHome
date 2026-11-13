import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button, Field } from "@/components/ui";
import { supabase } from "@/lib/supabase";

/**
 * Change your own password, from inside a signed-in session. Opened from the
 * "Change password" button on Settings, as a small card, and closed again once
 * the new password is saved or the person cancels.
 *
 * Why here and not a reset email: staff sign in as firstname@induduzo.co.za,
 * and most of those addresses have no mailbox, so a reset link would go
 * nowhere. An owner creates the account with a temporary password, tells the
 * person by phone or in person, and they replace it here on first sign-in.
 *
 * Reaching this screen already took the password AND the second step, so the
 * session itself is the proof of identity. Supabase stores the new password;
 * it never passes through our API, and we never log it.
 */

const MIN_LENGTH = 12;

interface ChangePasswordProps {
  id?: string;
  onCancel: () => void;
  onChanged: () => void;
}

export default function ChangePassword({ id, onCancel, onChanged }: ChangePasswordProps) {
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const card = useRef<HTMLElement>(null);

  // Opening the form moves the cursor into it, so the first key types the password.
  useEffect(() => {
    card.current?.querySelector("input")?.focus();
  }, []);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (next.length < MIN_LENGTH) {
      setError(`Use at least ${MIN_LENGTH} characters.`);
      return;
    }
    if (next !== again) {
      setError("The two passwords do not match.");
      return;
    }
    if (!supabase) {
      setError("Sign-in is not configured.");
      return;
    }

    setBusy(true);
    setError(null);
    const { error: updateError } = await supabase.auth.updateUser({ password: next });
    setBusy(false);

    if (updateError) {
      // Supabase's own wording (too weak, same as the old one, sign in again)
      // is clear and contains no personal data.
      setError(updateError.message || "That password could not be saved. Try another.");
      return;
    }
    setNext("");
    setAgain("");
    onChanged();
  };

  return (
    <section className="card" id={id} ref={card} style={{ maxWidth: 480 }}>
      <div className="card-head">
        <h2 className="t-section">Change your password</h2>
      </div>
      <form onSubmit={onSubmit} className="stack-8">
        <p className="t-small muted" style={{ margin: 0 }}>
          At least {MIN_LENGTH} characters; a short sentence is easiest to remember.
        </p>
        <Field
          label="New password"
          type="password"
          autoComplete="new-password"
          required
          value={next}
          onChange={setNext}
        />
        <Field
          label="New password again"
          type="password"
          autoComplete="new-password"
          required
          value={again}
          onChange={setAgain}
          error={error ?? undefined}
        />
        <div className="row">
          <Button variant="primary" type="submit" loading={busy} loadingLabel="Saving…">
            Save new password
          </Button>
          <Button variant="ghost" type="button" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
        </div>
      </form>
    </section>
  );
}
