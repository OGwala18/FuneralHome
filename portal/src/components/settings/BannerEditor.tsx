import { useEffect, useRef, useState, type ChangeEvent } from "react";
import {
  ApiError,
  fetchBannerImage,
  fetchWebsiteBanner,
  saveWebsiteBanner,
  uploadBannerImage,
  type WebsiteBannerAdmin,
} from "@/lib/api";
import {
  BANNER_HEIGHT,
  BANNER_WIDTH,
  cropForBanner,
  readPhoto,
  SHARP_ENOUGH_WIDTH,
  type SourcePhoto,
} from "@/lib/bannerPhoto";
import { formatDate } from "@/lib/derive";
import siteHero from "@/assets/site-hero-sunrise.jpg";
import { Button, Field, Notice, Skeleton } from "@/components/ui";

/**
 * The homepage banner: the big photo at the top of induduzo.co.za and the two
 * lines of words over it.
 *
 * Saving publishes it. The website asks the API for the banner on every page
 * load (cached for a minute), so there is no deploy and no developer. A blank
 * line keeps the website's own wording, shown here as the placeholder, so
 * staff can see exactly what blank means. "Use the standard banner" saves
 * everything blank.
 */

// The website's own words (frontend/src/lib/i18n.ts hero_title / hero_subtitle).
const STANDARD = {
  headline_en: "Dignified care when it matters most",
  headline_zu: "Ukunakekelwa ngenhlonipho lapho kudingeka khona kakhulu",
  message_en: "Serving Pietermaritzburg and the KZN Midlands with compassion since 1998",
  message_zu: "Sikhonza ePietermaritzburg nase-KZN Midlands ngomusa kusukela ngo-1998",
};

type Words = { headline_en: string; headline_zu: string; message_en: string; message_zu: string };

/** What the photo will be once saved. */
type Photo =
  | { kind: "standard" }
  | { kind: "saved"; id: string }
  | { kind: "new"; source: SourcePhoto; name: string };

const blankToNull = (value: string) => value.trim() || null;

export default function BannerEditor() {
  const [data, setData] = useState<WebsiteBannerAdmin | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [words, setWords] = useState<Words>({ headline_en: "", headline_zu: "", message_en: "", message_zu: "" });
  const [photo, setPhoto] = useState<Photo>({ kind: "standard" });
  const [focus, setFocus] = useState({ x: 0.5, y: 0.5 });
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [published, setPublished] = useState(false);
  const croppedRef = useRef<Blob | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = () => {
    setLoadError(null);
    fetchWebsiteBanner()
      .then((next) => {
        setData(next);
        const c = next.current;
        setWords({
          headline_en: c.headline_en ?? "", headline_zu: c.headline_zu ?? "",
          message_en: c.message_en ?? "", message_zu: c.message_zu ?? "",
        });
        setPhoto(c.image_id ? { kind: "saved", id: c.image_id } : { kind: "standard" });
      })
      .catch((error) => setLoadError(error instanceof Error ? error.message : String(error)));
  };

  useEffect(load, []);

  // The preview image: the standard photo, a saved one fetched with the staff
  // token, or the new photo cropped right here.
  useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    const show = (blob: Blob) => {
      if (cancelled) return;
      revoked = URL.createObjectURL(blob);
      setPreviewUrl(revoked);
    };
    croppedRef.current = null;
    setPhotoError(null);
    if (photo.kind === "standard") {
      setPreviewUrl(siteHero);
    } else if (photo.kind === "saved") {
      fetchBannerImage(photo.id).then(show).catch((error) => {
        if (!cancelled) setPhotoError(error instanceof Error ? error.message : String(error));
      });
    } else {
      setPreparing(true);
      cropForBanner(photo.source, focus.x, focus.y)
        .then((blob) => {
          croppedRef.current = blob;
          show(blob);
        })
        .catch((error) => !cancelled && setPhotoError(error instanceof Error ? error.message : String(error)))
        .finally(() => !cancelled && setPreparing(false));
    }
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [photo, focus]);

  if (loadError) {
    return (
      <Notice tone="error" title="Could not load the banner." detail={loadError}
        action={<Button small onClick={load}>Try again</Button>} />
    );
  }
  if (!data) return <section className="card"><Skeleton rows={6} /></section>;

  const canEdit = data.can_edit;
  const set = (key: keyof Words) => (value: string) => {
    setWords((w) => ({ ...w, [key]: value }));
    setPublished(false);
  };

  const choosePhoto = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const source = await readPhoto(file);
      setFocus({ x: 0.5, y: 0.5 });
      setPhoto({ kind: "new", source, name: file.name });
      setPublished(false);
    } catch (error) {
      setPhotoError(error instanceof Error ? error.message : String(error));
    }
  };

  const publish = async (standard = false) => {
    setSaving(true);
    setSaveError(null);
    setFieldErrors({});
    try {
      let imageId: string | null = null;
      if (!standard && photo.kind === "saved") imageId = photo.id;
      if (!standard && photo.kind === "new") {
        const blob = croppedRef.current ?? (await cropForBanner(photo.source, focus.x, focus.y));
        imageId = (await uploadBannerImage(blob)).id;
      }
      await saveWebsiteBanner(standard
        ? { headline_en: null, headline_zu: null, message_en: null, message_zu: null, image_id: null }
        : {
          headline_en: blankToNull(words.headline_en), headline_zu: blankToNull(words.headline_zu),
          message_en: blankToNull(words.message_en), message_zu: blankToNull(words.message_zu),
          image_id: imageId,
        });
      setPublished(true);
      load();
    } catch (error) {
      if (error instanceof ApiError) setFieldErrors(error.fieldErrors);
      setSaveError(error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  };

  const headline = words.headline_en.trim() || STANDARD.headline_en;
  const message = words.message_en.trim() || STANDARD.message_en;
  const isNew = photo.kind === "new";
  const wide = isNew && photo.source.width / photo.source.height > BANNER_WIDTH / BANNER_HEIGHT;
  const soft = isNew && photo.source.width < SHARP_ENOUGH_WIDTH;
  const current = data.current;

  return (
    <section className="card stack" aria-labelledby="banner-title">
      <div className="card-head">
        <div className="stack-8">
          <h2 className="t-title" id="banner-title">Homepage banner</h2>
          <p className="t-small muted">
            The photo and words at the top of induduzo.co.za. Publishing puts them on the
            website within a minute.
            {current.updated_at && data.history[0] &&
              ` Last changed ${formatDate(current.updated_at)} by ${data.history[0].saved_by}.`}
          </p>
        </div>
      </div>

      {published && (
        <Notice tone="success" title="Published"
          detail="The website shows the new banner within a minute. Refresh induduzo.co.za to check." />
      )}
      {!canEdit && (
        <Notice title="You can look but not change it"
          detail="Admins and owners publish the banner. Ask one if it needs to change." />
      )}

      {/* What families will see, at computer and phone sizes. */}
      <div className="banner-previews" aria-label="Preview">
        <figure className="stack-8">
          <div className="banner-preview banner-preview-wide"
            style={{ backgroundImage: previewUrl ? `url(${previewUrl})` : undefined }}>
            <div className="banner-preview-text">
              <strong>{headline}</strong>
              <span>{message}</span>
            </div>
          </div>
          <figcaption className="t-micro">On a computer</figcaption>
        </figure>
        <figure className="stack-8">
          <div className="banner-preview banner-preview-phone"
            style={{ backgroundImage: previewUrl ? `url(${previewUrl})` : undefined }}>
            <div className="banner-preview-text">
              <strong>{headline}</strong>
              <span>{message}</span>
            </div>
          </div>
          <figcaption className="t-micro">On a phone</figcaption>
        </figure>
      </div>

      <div className="stack">
        <h3 className="t-label">Photo</h3>
        <p className="t-small muted">
          {photo.kind === "standard" && "The website's own sunrise photo."}
          {photo.kind === "saved" && current.image_width &&
            `Your photo, ${current.image_width} × ${current.image_height} pixels.`}
          {isNew && `${photo.name}: cut and resized to ${BANNER_WIDTH} × ${BANNER_HEIGHT} pixels for the banner.`}
          {" "}Any photo works: it is cut to the banner's shape ({BANNER_WIDTH} × {BANNER_HEIGHT}) for you.
          Landscape photos at least {SHARP_ENOUGH_WIDTH} pixels wide look best.
        </p>
        {soft && (
          <Notice tone="warn" title="This photo is small"
            detail="It will look soft on a big screen. A larger photo of the same scene would be sharper." />
        )}
        {photoError && <Notice tone="error" title="Photo problem" detail={photoError} />}

        {isNew && (
          <div className="form-grid">
            <label className="field">
              <span>{wide ? "Keep which part? Left ↔ right" : "Keep which part? Top ↕ bottom"}</span>
              <input type="range" min={0} max={100} step={1}
                value={Math.round((wide ? focus.x : focus.y) * 100)}
                disabled={preparing}
                onChange={(e) => {
                  const value = Number(e.target.value) / 100;
                  setFocus((f) => (wide ? { ...f, x: value } : { ...f, y: value }));
                }} />
              <span className="field-hint">Slide until the important part of the photo is in the preview.</span>
            </label>
          </div>
        )}

        {canEdit && (
          <div className="row">
            <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp"
              className="sr-only" onChange={(e) => void choosePhoto(e)} />
            <Button onClick={() => fileInput.current?.click()}>
              {photo.kind === "standard" ? "Choose a photo" : "Choose a different photo"}
            </Button>
            {photo.kind !== "standard" && (
              <Button variant="ghost" onClick={() => { setPhoto({ kind: "standard" }); setPublished(false); }}>
                Use the website's own photo
              </Button>
            )}
          </div>
        )}
      </div>

      <div className="stack">
        <h3 className="t-label">Words</h3>
        <p className="t-small muted">Leave a line blank to keep the website's own wording, shown in grey.</p>
        <div className="form-grid">
          <Field label="Headline (English)" value={words.headline_en} onChange={set("headline_en")}
            placeholder={STANDARD.headline_en} disabled={!canEdit}
            error={fieldErrors.headline_en} hint={`${words.headline_en.length}/120`} />
          <Field label="Headline (isiZulu)" value={words.headline_zu} onChange={set("headline_zu")}
            placeholder={STANDARD.headline_zu} disabled={!canEdit}
            error={fieldErrors.headline_zu} hint="Optional. Blank shows the English headline you typed." />
        </div>
        <div className="form-grid">
          <Field label="Message (English)" value={words.message_en} onChange={set("message_en")}
            placeholder={STANDARD.message_en} disabled={!canEdit}
            error={fieldErrors.message_en} hint={`${words.message_en.length}/300`} />
          <Field label="Message (isiZulu)" value={words.message_zu} onChange={set("message_zu")}
            placeholder={STANDARD.message_zu} disabled={!canEdit}
            error={fieldErrors.message_zu} hint="Optional. Blank shows the English message you typed." />
        </div>
      </div>

      {saveError && <Notice tone="error" title="Not published" detail={saveError} />}

      {canEdit && (
        <div className="row row-between">
          <Button variant="ghost" disabled={saving} onClick={() => void publish(true)}>
            Use the standard banner
          </Button>
          <Button variant="primary" loading={saving} loadingLabel="Publishing…" disabled={preparing}
            onClick={() => void publish(false)}>
            Publish to the website
          </Button>
        </div>
      )}

      {data.history.length > 1 && (
        <details>
          <summary className="t-small">Recent changes</summary>
          <ul className="t-small muted stack-8" style={{ marginTop: "var(--s12)" }}>
            {data.history.map((change) => (
              <li key={change.id}>
                {change.updated_at && formatDate(change.updated_at)} · {change.saved_by} ·{" "}
                {change.headline_en || change.image_id || change.message_en
                  ? `“${change.headline_en ?? "standard headline"}”${change.image_id ? ", own photo" : ""}`
                  : "standard banner"}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
