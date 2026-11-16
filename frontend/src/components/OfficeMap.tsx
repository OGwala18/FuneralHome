import { useId, useState } from "react";
import { MapPin } from "lucide-react";

import { useLanguage } from "@/lib/i18n";
import { BRANCHES, mapEmbedSrc, mapLink, type BranchId } from "@/lib/location";

type OfficeMapProps = {
  className?: string;
  height?: string;
};

const SELECT_CLASS =
  "flex h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-base " +
  "ring-offset-background focus-visible:outline-none focus-visible:ring-2 " +
  "focus-visible:ring-ring focus-visible:ring-offset-2";

/**
 * A branch picker, the chosen branch's address as a link to whichever map app
 * the device has, and the map itself directly underneath. It opens on the head
 * office; choosing another branch moves the map there.
 *
 * The iframe is lazy — it is below the fold on every surface that uses it, and
 * a map is a heavy thing to load for a visitor who only wanted a phone number.
 */
export function OfficeMap({ className = "", height = "h-64" }: OfficeMapProps) {
  const { language, t } = useLanguage();
  const [branchId, setBranchId] = useState<BranchId>(BRANCHES[0].id);
  const pickerId = useId();
  const branch = BRANCHES.find((b) => b.id === branchId) ?? BRANCHES[0];
  const name = (b: (typeof BRANCHES)[number]) => (language === "en" ? b.name_en : b.name_zu);

  return (
    <div className={className}>
      <label htmlFor={pickerId} className="mb-1.5 block text-sm font-medium">
        {t("map_choose_branch")}
      </label>
      <select
        id={pickerId}
        value={branchId}
        onChange={(event) => setBranchId(event.target.value as BranchId)}
        className={SELECT_CLASS}
      >
        {BRANCHES.map((b) => (
          <option key={b.id} value={b.id}>{name(b)}</option>
        ))}
      </select>

      <a
        href={mapLink(branch)}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-3 inline-flex items-start rounded text-left hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <MapPin className="mr-2 mt-1 h-5 w-5 flex-shrink-0" aria-hidden="true" />
        <span aria-live="polite">
          {branch.lines.map((line) => (
            <span key={line} className="block">{line}</span>
          ))}
          <span className="mt-1 block text-sm font-medium underline">
            {t("contact_directions")}
          </span>
        </span>
      </a>

      <iframe
        // A new key per branch, so the browser loads the new map rather than
        // keeping the old frame's history.
        key={branch.id}
        title={`${t("contact_map_label")}: ${name(branch)}`}
        src={mapEmbedSrc(branch)}
        loading="lazy"
        referrerPolicy="no-referrer-when-downgrade"
        allowFullScreen
        className={`mt-4 w-full rounded-md border ${height}`}
      />
    </div>
  );
}
