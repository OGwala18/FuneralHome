import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchEscalation,
  fetchEscalations,
  fetchWhatsAppMedia,
  replyToEscalation,
  resolveEscalation,
  type WhatsAppConversation,
  type WhatsAppEscalation,
  type WhatsAppMessage,
} from "@/lib/api";
import { formatDate } from "@/lib/derive";
import { hrefFor, navigate } from "@/lib/router";
import { Badge, Button, Empty, Fact, Notice, Skeleton } from "@/components/ui";

/**
 * WhatsApp families who asked for a person.
 *
 * The WhatsApp menu answers most questions on its own, and none of that shows
 * here. A conversation appears only once a family picks "a person, please":
 * that is when the office is emailed, and when staff may write back from the
 * line's own number. WhatsApp allows free text for 24 hours after the family's
 * last message; after that the screen says to phone instead.
 *
 * Laid out like Today: the queue on the left, the conversation being worked on
 * beside it.
 */

const LIST_POLL_MS = 60_000;
const CONVERSATION_POLL_MS = 20_000;

const sinceText = (iso: string): string => {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return formatDate(iso);
};

const timeText = (iso: string) =>
  new Date(iso).toLocaleString("en-ZA", {
    weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });

const asked = (row: WhatsAppEscalation) =>
  row.channel === "whatsapp" ? "A WhatsApp reply" : "A phone call";

/* ---------------------------------------------------------------- Queue --- */

function Queue({
  rows, selectedId, view,
}: { rows: WhatsAppEscalation[]; selectedId?: string; view: "open" | "resolved" }) {
  if (rows.length === 0) {
    return view === "open" ? (
      <Empty title="Nobody is waiting">
        When a family asks the WhatsApp menu for a person, they appear here and the office is emailed.
      </Empty>
    ) : (
      <Empty title="Nothing resolved yet" />
    );
  }

  return (
    <div className="stack-8">
      {rows.map((row) => (
        <button
          type="button"
          key={row.id}
          className="queue-item"
          aria-current={selectedId === row.id}
          onClick={() => navigate({ name: "whatsapp", id: row.id })}
        >
          <div className="row row-between" style={{ gap: "var(--s8)" }}>
            <span className="queue-name">{row.name}</span>
            {row.unanswered > 0 && row.status === "open" && (
              <Badge tone="due">{row.unanswered} new</Badge>
            )}
          </div>
          <div className="row" style={{ gap: "var(--s8)", marginTop: 2, flexWrap: "wrap" }}>
            {row.urgent ? <Badge tone="overdue">Someone has passed away</Badge>
              : <span className="t-small muted">{row.topic_label}</span>}
            <span className="t-small muted">·</span>
            <span className="t-small muted">
              {row.status === "open" ? sinceText(row.requested_at) : `Resolved ${sinceText(row.resolved_at!)}`}
            </span>
          </div>
          <span className="t-small muted">
            {asked(row)}
            {row.out_of_hours && row.status === "open" ? " · asked after hours" : ""}
          </span>
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------ Messages --- */

function Attachment({ message, index, type }: { message: WhatsAppMessage; index: number; type: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  const open = () => {
    setLoading(true);
    setError(null);
    fetchWhatsAppMedia(message.id, index)
      .then((blob) => setUrl(URL.createObjectURL(blob)))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not open it."))
      .finally(() => setLoading(false));
  };

  const label = type.startsWith("image/") ? "Photo" : type === "application/pdf" ? "PDF" : "File";

  if (url && type.startsWith("image/")) {
    return <img className="bubble-image" src={url} alt="Photo the family sent" />;
  }
  if (url) {
    return <a href={url} download={`whatsapp-${message.id}-${index}`}>Download {label.toLowerCase()}</a>;
  }
  return (
    <span className="stack-8">
      <Button small onClick={open} loading={loading} loadingLabel="Opening…">Open {label.toLowerCase()}</Button>
      {error && <span className="t-small">{error}</span>}
    </span>
  );
}

const STATUS_TEXT: Record<string, string> = {
  not_sent: "Not sent",
  queued: "Sending",
  sent: "Sent",
  delivered: "Delivered",
  read: "Read",
  failed: "Failed",
  undelivered: "Not delivered",
};

function Bubble({ message }: { message: WhatsAppMessage }) {
  const fromFamily = message.direction === "inbound";
  const automatic = message.author === "menu" || message.author === "system";
  const kind = fromFamily ? "family" : automatic ? "menu" : "staff";
  const who = fromFamily ? "Family" : message.author === "menu" ? "WhatsApp menu"
    : message.author === "system" ? "Registration confirmation" : message.author;
  // WhatsApp shows *these* in bold; here the stars would just be noise.
  const body = (message.body ?? "").replace(/\*([^*\n]+)\*/g, "$1");
  const [firstLine, ...rest] = body.split("\n");

  return (
    <div className={`bubble bubble-${kind}`}>
      {automatic && rest.length > 0 ? (
        <details>
          <summary>{firstLine}</summary>
          <span>{rest.join("\n")}</span>
        </details>
      ) : (
        body && <span>{body}</span>
      )}
      {message.media.map((m, i) => (
        <Attachment key={m.sid} message={message} index={i} type={m.content_type} />
      ))}
      <span className="bubble-meta">
        {who} · {timeText(message.created_at)}
        {!fromFamily && ` · ${STATUS_TEXT[message.status] ?? message.status}`}
        {message.error_code && ` (${message.error_code})`}
      </span>
    </div>
  );
}

/* -------------------------------------------------------- Conversation --- */

function Conversation({
  id, canEdit, onChanged,
}: { id: string; canEdit: boolean; onChanged: () => void }) {
  const [conversation, setConversation] = useState<WhatsAppConversation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [askRating, setAskRating] = useState(true);
  const [resolving, setResolving] = useState(false);
  const transcript = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    fetchEscalation(id)
      .then((next) => { setConversation(next); setError(null); })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the conversation."));
  }, [id]);

  useEffect(() => {
    setConversation(null);
    load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, CONVERSATION_POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  const count = conversation?.messages.length ?? 0;
  useEffect(() => {
    transcript.current?.scrollTo({ top: transcript.current.scrollHeight });
  }, [count]);

  if (error && !conversation) {
    return <Notice tone="error" title="Could not load the conversation." detail={error}
      action={<Button small onClick={load}>Try again</Button>} />;
  }
  if (!conversation) return <Skeleton rows={8} />;

  const c = conversation;
  const open = c.status === "open";

  const send = () => {
    const body = draft.trim();
    if (!body) return;
    setSending(true);
    setSendError(null);
    replyToEscalation(c.id, body)
      .then(() => { setDraft(""); load(); onChanged(); })
      .catch((err) => {
        setSendError(err instanceof ApiError ? err.message : "The message didn't send.");
        // A refused reply is still recorded, marked not sent.
        load();
      })
      .finally(() => setSending(false));
  };

  const resolve = () => {
    setResolving(true);
    resolveEscalation(c.id, { note: note.trim() || undefined, ask_rating: askRating })
      .then(() => { setNote(""); load(); onChanged(); })
      .catch((err) => setSendError(err instanceof ApiError ? err.message : "Could not resolve it."))
      .finally(() => setResolving(false));
  };

  return (
    <div className="stack" style={{ gap: "var(--s20)" }}>
      <div className="row row-between" style={{ alignItems: "flex-start", gap: "var(--s16)", flexWrap: "wrap" }}>
        <div className="stack-8">
          <h2 className="t-title">{c.name}</h2>
          <div className="row" style={{ gap: "var(--s8)", flexWrap: "wrap" }}>
            {c.urgent && <Badge tone="overdue">Someone has passed away</Badge>}
            <Badge tone={open ? "due" : "success"}>{open ? "Waiting" : "Resolved"}</Badge>
            {!c.urgent && <span className="t-small muted">{c.topic_label}</span>}
          </div>
        </div>
        <a className="btn btn-primary" href={`tel:${c.other_number}`}>Call {c.other_number}</a>
      </div>

      <div className="fact-grid">
        <Fact label="They asked for">{asked(c)}</Fact>
        <Fact label="Asked">{timeText(c.requested_at)}</Fact>
        {c.out_of_hours && c.promised_for && (
          <Fact label="We promised">{timeText(c.promised_for)}</Fact>
        )}
        {c.enquiry_id && (
          <Fact label="Enquiry">
            <a href={hrefFor({ name: "person", id: c.enquiry_id })}
              onClick={(e) => { e.preventDefault(); navigate({ name: "person", id: c.enquiry_id! }); }}>
              <span className="ref">{c.enquiry_reference}</span>
            </a>
          </Fact>
        )}
        {c.person_id && (
          <Fact label="Member">
            <a href={hrefFor({ name: "member", id: c.person_id })}
              onClick={(e) => { e.preventDefault(); navigate({ name: "member", id: c.person_id! }); }}>
              {c.member_name}
            </a>
          </Fact>
        )}
        {c.profile_name && <Fact label="WhatsApp name">{c.profile_name}</Fact>}
        {!open && c.resolved_by && <Fact label="Resolved by">{c.resolved_by}</Fact>}
      </div>

      {!open && c.resolution_note && <Notice tone="success" title="Resolved" detail={c.resolution_note} />}

      <div className="transcript" ref={transcript} aria-label="Messages">
        {c.messages.map((m) => <Bubble key={m.id} message={m} />)}
      </div>

      {open && canEdit && (
        c.window_open ? (
          <div className="stack-8">
            <div className={`field${sendError ? " field-error" : ""}`}>
              <label htmlFor="wa-reply">Reply on WhatsApp</label>
              <textarea
                id="wa-reply"
                rows={3}
                maxLength={1600}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Sent from the Induduzo WhatsApp line. Never ask for ID numbers or bank details here."
              />
              <span className="field-hint" role={sendError ? "alert" : undefined}>
                {sendError ?? `${draft.length} / 1600`}
              </span>
            </div>
            <div className="row" style={{ gap: "var(--s8)" }}>
              <Button onClick={send} loading={sending} loadingLabel="Sending…" disabled={!draft.trim()}>
                Send reply
              </Button>
            </div>
          </div>
        ) : (
          <Notice tone="warn" title="Phone them instead"
            detail="It's been more than 24 hours since they last wrote, so WhatsApp only allows approved templates now. If they message again, you can reply here." />
        )
      )}

      {open && canEdit && (
        <div className="card card-tight stack-8" style={{ background: "var(--paper)" }}>
          <span className="t-label">When it's dealt with</span>
          <div className="field">
            <label htmlFor="wa-note">Note for the record (optional)</label>
            <textarea id="wa-note" rows={2} maxLength={1000} value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="For example: phoned her, explained the claim documents." />
            <span className="field-hint" />
          </div>
          <label className="row" style={{ gap: "var(--s8)" }}>
            <input type="checkbox" checked={askRating} onChange={(e) => setAskRating(e.target.checked)}
              disabled={!c.window_open} />
            <span className="t-small">
              Ask them to rate our help{c.window_open ? "" : " (not possible after 24 hours)"}
            </span>
          </label>
          <div>
            <Button onClick={resolve} loading={resolving} loadingLabel="Resolving…">Mark resolved</Button>
          </div>
        </div>
      )}

      {open && !canEdit && (
        <p className="t-small muted" style={{ margin: 0 }}>
          Viewers can read conversations. Replying and resolving need an admin.
        </p>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------- Page --- */

export default function WhatsApp({ id, canEdit }: { id?: string; canEdit: boolean }) {
  const [view, setView] = useState<"open" | "resolved">("open");
  const [rows, setRows] = useState<WhatsAppEscalation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetchEscalations(view)
        .then((next) => { if (!cancelled) { setRows(next); setError(null); } })
        .catch((err) => {
          if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load WhatsApp.");
        })
        .finally(() => { if (!cancelled) setLoading(false); });
    };
    setLoading(true);
    load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, LIST_POLL_MS);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [view, reload]);

  const selectedId = id ?? rows[0]?.id;

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-text">
          <a className="t-small" href={hrefFor({ name: "growth" })}
            onClick={(e) => { e.preventDefault(); navigate({ name: "growth" }); }}>
            ← Growth
          </a>
          <h1 className="t-heading">WhatsApp</h1>
          <p className="muted">
            Families who asked the WhatsApp menu for a person. Everything else the menu answers on
            its own, and isn't shown here.
          </p>
        </div>
        <div className="row" style={{ gap: "var(--s8)" }}>
          <Button small variant={view === "open" ? "selected" : "secondary"} onClick={() => setView("open")}>
            Waiting
          </Button>
          <Button small variant={view === "resolved" ? "selected" : "secondary"} onClick={() => setView("resolved")}>
            Resolved
          </Button>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: "var(--s16)" }}>
          <Notice tone="error" title="Could not load WhatsApp." detail={error}
            action={<Button small onClick={() => setReload((n) => n + 1)}>Try again</Button>} />
        </div>
      )}

      <div className="inbox">
        <aside className="card" aria-label={view === "open" ? "Waiting for a person" : "Resolved"}>
          {loading && rows.length === 0 ? <Skeleton rows={6} />
            : <Queue rows={rows} selectedId={selectedId} view={view} />}
        </aside>
        <section className="card">
          {selectedId ? (
            <Conversation key={selectedId} id={selectedId} canEdit={canEdit}
              onChanged={() => setReload((n) => n + 1)} />
          ) : (
            <Empty title="Choose a conversation">
              Pick a family on the left to read what they asked and reply.
            </Empty>
          )}
        </section>
      </div>
    </div>
  );
}
