import logoPng from "@/assets/logo-primary-gold.png";
import logoWebp from "@/assets/logo-primary-gold.webp";

/**
 * The primary Induduzo logo, in metallic gold.
 *
 * Brand guide 2025, "Logo on white": on a light surface use the metallic gold
 * (#C9A04B) version, never the bright-gold on-black artwork, and never recolour
 * it. The wordmark is built in, so no "Induduzo Funeral Home" text sits beside
 * it; the alt text carries the name for screen readers and search engines.
 *
 * The files are cut from the brand guide's own artwork at 192px tall, three
 * times the largest size the site shows it, so it stays sharp on phones.
 */
export function BrandLogo({ className = "" }: { className?: string }) {
  return (
    <picture>
      <source srcSet={logoWebp} type="image/webp" />
      <img
        src={logoPng}
        alt="Induduzo Funeral Home"
        width={314}
        height={192}
        className={`w-auto ${className}`}
        decoding="async"
      />
    </picture>
  );
}
