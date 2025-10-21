import { NavLink } from "react-router-dom";
import { Phone } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import React, { useState } from 'react';

function ServicesDropdown() {
  const [open, setOpen] = useState(false);
  const { t } = useLanguage();
  const buttonId = "services-button";
  const menuId = "services-menu";
  
  return (
    <div
      className="nav-dropdown"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      style={{ position: 'relative' }}
    >
      <button
        id={buttonId}
        aria-haspopup="menu"
        aria-expanded={open ? 'true' : 'false'}
        aria-controls={menuId}
        style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'inherit', fontSize: 'inherit', fontWeight: 'inherit' }}
        className="hover:text-primary transition-colors"
      >
        {t("nav_services")} ▾
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-labelledby={buttonId}
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            background: '#fff',
            border: '1px solid #eee',
            borderRadius: 6,
            minWidth: 180,
            boxShadow: '0 6px 20px rgba(0,0,0,.06)',
            padding: '.25rem',
            zIndex: 50
          }}
        >
          <NavLink to="/services" role="menuitem" style={itemStyle} className="block rounded hover:text-primary transition-colors">
            {t("nav_services")}
          </NavLink>
          <NavLink to="/gallery" role="menuitem" style={itemStyle} className="block rounded hover:text-primary transition-colors">
            Gallery
          </NavLink>
          <NavLink to="/testimonials" role="menuitem" style={itemStyle} className="block rounded hover:text-primary transition-colors">
            Testimonials
          </NavLink>
        </div>
      )}
    </div>
  );
}

function AboutDropdown() {
  const [open, setOpen] = useState(false);
  const { t } = useLanguage();
  const buttonId = "about-button";
  const menuId = "about-menu";

  return (
    <div
      className="nav-dropdown"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      style={{ position: 'relative' }}
    >
      <button
        id={buttonId}
        aria-haspopup="menu"
        aria-expanded={open ? 'true' : 'false'}
        aria-controls={menuId}
        style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'inherit', fontSize: 'inherit', fontWeight: 'inherit' }}
        className="hover:text-primary transition-colors"
      >
        {t("nav_about")} ▾
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-labelledby={buttonId}
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            background: '#fff',
            border: '1px solid #eee',
            borderRadius: 6,
            minWidth: 180,
            boxShadow: '0 6px 20px rgba(0,0,0,.06)',
            padding: '.25rem',
            zIndex: 50
          }}
        >
          <NavLink to="/about" role="menuitem" style={itemStyle} className="block rounded hover:text-primary transition-colors">
            {t("nav_about")}
          </NavLink>
          <NavLink to="/founder" role="menuitem" style={itemStyle} className="block rounded hover:text-primary transition-colors">
            Founder Story
          </NavLink>
        </div>
      )}
    </div>
  );
}

const itemStyle: React.CSSProperties = {
  display: 'block',
  padding: '.5rem .75rem',
  textDecoration: 'none',
  borderRadius: 4
};

export const Header = () => {
  const { language, switchLanguage, t } = useLanguage();

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="container flex h-16 items-center justify-between">
        <NavLink to="/" className="flex items-center space-x-2">
          <div className="text-2xl font-bold text-primary">Induduzo</div>
        </NavLink>

        <nav className="hidden md:flex items-center space-x-6 text-base font-medium">
          <NavLink
            to="/"
            className={({ isActive }) =>
              `hover:text-primary transition-colors ${isActive ? "text-primary font-semibold" : "text-foreground"}`
            }
          >
            {t("nav_home")}
          </NavLink>
          <AboutDropdown />
          <ServicesDropdown />
          <NavLink
            to="/contact"
            className={({ isActive }) =>
              `hover:text-primary transition-colors ${isActive ? "text-primary font-semibold" : "text-foreground"}`
            }
          >
            {t("nav_contact")}
          </NavLink>
          <NavLink
            to="/join"
            className={({ isActive }) =>
              `hover:text-primary transition-colors ${isActive ? "text-primary font-semibold" : "text-foreground"}`
            }
          >
            {t("nav_join")}
          </NavLink>
        </nav>

        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-1 text-sm">
            <button
              onClick={() => switchLanguage('en')}
              className={`px-2 py-1 rounded ${language === 'en' ? 'bg-primary text-primary-foreground font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
            >
              EN
            </button>
            <span className="text-muted-foreground">|</span>
            <button
              onClick={() => switchLanguage('zu')}
              className={`px-2 py-1 rounded ${language === 'zu' ? 'bg-primary text-primary-foreground font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
            >
              ZU
            </button>
          </div>

          <Button asChild size="sm" className="hidden md:flex">
            <a href="tel:0829549241">
              <Phone className="mr-2 h-4 w-4" />
              {t("cta_call")}
            </a>
          </Button>
        </div>
      </div>
    </header>
  );
};
