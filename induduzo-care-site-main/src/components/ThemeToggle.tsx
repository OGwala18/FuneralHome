import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/lib/theme";
import { useLanguage } from "@/lib/i18n";

interface ThemeToggleProps {
  className?: string;
}

/**
 * Light/dark switch.
 *
 * A single button rather than a menu: there are two states, so a menu would be
 * one more click for no gain. The icon shows what you will GET, not what you
 * are in — the label says which, so nobody has to guess from the pictogram.
 */
export function ThemeToggle({ className = "" }: ThemeToggleProps) {
  const { theme, toggleTheme } = useTheme();
  const { language } = useLanguage();
  const en = language === "en";
  const goingDark = theme === "light";

  const label = goingDark
    ? en
      ? "Switch to dark mode"
      : "Shintshela kumbala omnyama"
    : en
      ? "Switch to light mode"
      : "Shintshela kumbala okhanyayo";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      title={label}
      aria-label={label}
      className={`inline-flex min-h-10 min-w-10 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${className}`}
    >
      {/* Both icons are rendered and cross-faded, so the swap does not pop.
          aria-hidden on both: the button's own label carries the meaning. */}
      <span className="relative block h-[18px] w-[18px]">
        <Moon
          aria-hidden="true"
          className={`absolute inset-0 h-[18px] w-[18px] transition-all duration-200 ${
            goingDark ? "scale-100 opacity-100" : "scale-90 opacity-0"
          }`}
        />
        <Sun
          aria-hidden="true"
          className={`absolute inset-0 h-[18px] w-[18px] transition-all duration-200 ${
            goingDark ? "scale-90 opacity-0" : "scale-100 opacity-100"
          }`}
        />
      </span>
    </button>
  );
}
