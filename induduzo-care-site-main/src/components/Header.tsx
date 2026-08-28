import React, { useState } from "react";
import { Menu, MessageCircle, Phone, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ThemeToggle";
import { CONTACT_PHONE_LINK, WHATSAPP_URL } from "@/lib/contact";
import { useLanguage } from "@/lib/i18n";
import { NavLink } from "@/lib/navigation";

type DropdownItem = {
  label: string;
  to: string;
};

type DesktopDropdownProps = {
  id: string;
  items: DropdownItem[];
  label: string;
};

function DesktopDropdown({ id, items, label }: DesktopDropdownProps) {
  const [open, setOpen] = useState(false);
  const menuId = `${id}-menu`;

  return (
    <div
      className="relative"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setOpen(false);
        }
      }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        id={id}
        type="button"
        aria-controls={menuId}
        aria-expanded={open}
        aria-haspopup="menu"
        className="rounded px-1 py-2 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onClick={(event) => {
          if (event.detail === 0) {
            setOpen((current) => !current);
          } else {
            setOpen(true);
          }
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setOpen(false);
          }
        }}
      >
        {label} <span aria-hidden="true">▾</span>
      </button>

      {open && (
        <div
          id={menuId}
          role="menu"
          aria-labelledby={id}
          className="absolute left-0 top-full z-50 min-w-48 rounded-md border bg-background p-1 shadow-lg"
        >
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              role="menuitem"
              className="block rounded px-3 py-2 hover:bg-secondary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setOpen(false)}
            >
              {item.label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

export const Header = () => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { language, switchLanguage, t } = useLanguage();
  const closeMobileMenu = () => setMobileOpen(false);

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded px-1 py-2 transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
      isActive ? "font-semibold text-primary" : "text-foreground"
    }`;

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="container flex h-16 items-center justify-between gap-2">
        <NavLink to="/" className="flex shrink-0 items-center" onClick={closeMobileMenu}>
          <span className="text-xl font-bold text-primary sm:text-2xl">Induduzo</span>
        </NavLink>

        <nav className="hidden items-center gap-4 text-sm font-medium lg:flex xl:gap-6 xl:text-base">
          <NavLink to="/" className={navLinkClass}>
            {t("nav_home")}
          </NavLink>
          <DesktopDropdown
            id="about-button"
            label={t("nav_about")}
            items={[
              { label: t("nav_about"), to: "/about" },
              { label: t("nav_founder"), to: "/founder" },
            ]}
          />
          <DesktopDropdown
            id="services-button"
            label={t("nav_services")}
            items={[
              { label: t("nav_services"), to: "/services" },
              { label: t("nav_gallery"), to: "/gallery" },
              { label: t("nav_testimonials"), to: "/testimonials" },
            ]}
          />
          <NavLink to="/contact" className={navLinkClass}>
            {t("nav_contact")}
          </NavLink>
          <NavLink to="/join" className={navLinkClass}>
            {t("nav_join")}
          </NavLink>
        </nav>

        <div className="flex shrink-0 items-center gap-1 sm:gap-3">
          <div className="flex items-center text-sm">
            <button
              type="button"
              aria-label="Use English"
              aria-pressed={language === "en"}
              onClick={() => switchLanguage("en")}
              className={`min-h-10 rounded px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                language === "en"
                  ? "bg-action font-semibold text-action-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <span className="sm:hidden">EN</span>
              <span className="hidden sm:inline">English</span>
            </button>
            <span className="text-muted-foreground" aria-hidden="true">
              |
            </span>
            <button
              type="button"
              aria-label="Use isiZulu"
              aria-pressed={language === "zu"}
              onClick={() => switchLanguage("zu")}
              className={`min-h-10 rounded px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                language === "zu"
                  ? "bg-action font-semibold text-action-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <span className="sm:hidden">ZU</span>
              <span className="hidden sm:inline">Zulu</span>
            </button>
          </div>

          <ThemeToggle />

          <Button asChild size="sm" className="hidden xl:inline-flex">
            <a href={CONTACT_PHONE_LINK}>
              <Phone className="mr-2 h-4 w-4" />
              {t("cta_call")}
            </a>
          </Button>

          <button
            type="button"
            aria-controls="mobile-navigation"
            aria-expanded={mobileOpen}
            aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border lg:hidden"
            onClick={() => setMobileOpen((current) => !current)}
          >
            {mobileOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
        </div>
      </div>

      {mobileOpen && (
        <nav id="mobile-navigation" aria-label="Mobile navigation" className="border-t bg-background lg:hidden">
          <div className="container grid gap-1 py-3">
            {[
              { label: t("nav_home"), to: "/" },
              { label: t("nav_about"), to: "/about" },
              { label: t("nav_founder"), to: "/founder" },
              { label: t("nav_services"), to: "/services" },
              { label: t("nav_gallery"), to: "/gallery" },
              { label: t("nav_testimonials"), to: "/testimonials" },
              { label: t("nav_contact"), to: "/contact" },
              { label: t("nav_join"), to: "/join" },
            ].map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className="rounded-md px-3 py-3 font-medium hover:bg-secondary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={closeMobileMenu}
              >
                {item.label}
              </NavLink>
            ))}

            <div className="mt-2 grid grid-cols-2 gap-2 border-t pt-3">
              <a
                href={CONTACT_PHONE_LINK}
                className="inline-flex min-h-11 items-center justify-center rounded-md bg-action px-3 text-sm font-semibold text-action-foreground"
              >
                <Phone className="mr-2 h-4 w-4" />
                {t("cta_call")}
              </a>
              <a
                href={WHATSAPP_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-11 items-center justify-center rounded-md bg-[#25D366] px-3 text-sm font-semibold text-white"
              >
                <MessageCircle className="mr-2 h-4 w-4" />
                WhatsApp
              </a>
            </div>
          </div>
        </nav>
      )}
    </header>
  );
};
