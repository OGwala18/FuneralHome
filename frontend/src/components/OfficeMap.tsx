import { MapPin } from "lucide-react";

import { useLanguage } from "@/lib/i18n";
import {
  OFFICE_ADDRESS_LINES,
  OFFICE_MAP_EMBED_SRC,
  OFFICE_MAP_LINK,
} from "@/lib/location";

type OfficeMapProps = {
  className?: string;
  height?: string;
  /** Off where the surrounding page already shows the address. */
  showAddress?: boolean;
};

/**
 * The office address as a link to whichever map app the device has, with the
 * map itself directly underneath.
 *
 * The iframe is lazy — it is below the fold on every surface that uses it, and
 * a map is a heavy thing to load for a visitor who only wanted a phone number.
 */
export function OfficeMap({
  className = "",
  height = "h-64",
  showAddress = true,
}: OfficeMapProps) {
  const { t } = useLanguage();

  return (
    <div className={className}>
      {showAddress && (
        <a
          href={OFFICE_MAP_LINK}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-start rounded text-left hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <MapPin
            className="mr-2 mt-1 h-5 w-5 flex-shrink-0"
            aria-hidden="true"
          />
          <span>
            {OFFICE_ADDRESS_LINES.map((line) => (
              <span key={line} className="block">
                {line}
              </span>
            ))}
            <span className="mt-1 block text-sm font-medium underline">
              {t("contact_directions")}
            </span>
          </span>
        </a>
      )}

      <iframe
        title={t("contact_map_label")}
        src={OFFICE_MAP_EMBED_SRC}
        loading="lazy"
        referrerPolicy="no-referrer-when-downgrade"
        allowFullScreen
        className={`w-full rounded-md border ${showAddress ? "mt-4" : ""} ${height}`}
      />
    </div>
  );
}
