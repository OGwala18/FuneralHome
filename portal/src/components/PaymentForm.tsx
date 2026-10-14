import { useState, type FormEvent } from "react";
import { ApiError, recordPayment, waiveInstalment, type PaymentMethod } from "@/lib/api";
import { formatMoney, toCents } from "@/lib/derive";
import { Button, Field, Select } from "./ui";

export const PAYMENT_METHODS: { value: PaymentMethod; label: string }[] = [
  { value: "debit_order", label: "Debit order" },
  { value: "stop_order", label: "Stop order" },
  { value: "eft", label: "EFT" },
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "easypay", label: "EasyPay" },
  { value: "payat", label: "Pay@" },
  { value: "undecided", label: "Not decided" },
];

/** Today in the office's own time zone, as YYYY-MM-DD. (toISOString is UTC.) */
export const today = () => new Date().toLocaleDateString("en-CA");

/**
 * Record that one instalment was paid, or waive it.
 *
 * Book-keeping only: when, how much, which method. There is no field for a
 * bank account or card number here, and there never should be.
 */
export default function PaymentForm({
  instalmentId,
  amountCents,
  currency,
  defaultMethod,
  onDone,
  onCancel,
}: {
  instalmentId: string;
  amountCents: number;
  currency: string;
  defaultMethod?: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [mode, setMode] = useState<"pay" | "waive">("pay");
  const [paidOn, setPaidOn] = useState(today());
  const [amount, setAmount] = useState((amountCents / 100).toFixed(2));
  const [method, setMethod] = useState<string>(
    defaultMethod && defaultMethod !== "undecided" ? defaultMethod : "cash");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setFieldErrors({});

    setSaving(true);
    try {
      if (mode === "pay") {
        const cents = toCents(amount);
        if (cents === null) {
          setFieldErrors({ amount_cents: "Enter an amount in rand, e.g. 250.00" });
          return;
        }
        await recordPayment(instalmentId, {
          paid_on: paidOn, amount_cents: cents, method: method as PaymentMethod,
        });
      } else {
        await waiveInstalment(instalmentId, reason);
      }
      onDone();
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors);
        setError(err.message);
      } else {
        setError("Could not save. Try again.");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="stack-8" onSubmit={submit}>
      <div className="row">
        <Button small type="button" variant={mode === "pay" ? "selected" : "ghost"}
          onClick={() => setMode("pay")}>Paid</Button>
        <Button small type="button" variant={mode === "waive" ? "selected" : "ghost"}
          onClick={() => setMode("waive")}>Waive</Button>
        <span className="t-small muted">Due: {formatMoney(amountCents, currency)}</span>
      </div>

      {mode === "pay" ? (
        <div className="form-grid">
          <Field label="Paid on" type="date" value={paidOn} onChange={setPaidOn}
            error={fieldErrors.paid_on} />
          <Field label="Amount (R)" value={amount} onChange={setAmount}
            error={fieldErrors.amount_cents} />
          <Select label="Method" value={method} onChange={setMethod}
            options={PAYMENT_METHODS} error={fieldErrors.method} />
        </div>
      ) : (
        <Field label="Why is it waived?" value={reason} onChange={setReason}
          hint="Recorded with your name, e.g. agreed payment holiday"
          error={fieldErrors.reason} />
      )}

      {error && <p className="t-small" style={{ color: "var(--red)", margin: 0 }} role="alert">{error}</p>}

      <div className="row">
        <Button small variant="primary" type="submit" loading={saving} loadingLabel="Saving…">
          {mode === "pay" ? "Record payment" : "Waive instalment"}
        </Button>
        <Button small type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}
