import { NavLink } from "react-router-dom";
import { Mail, Phone, MapPin } from "lucide-react";
import { useLanguage } from "@/lib/i18n";

export const Footer = () => {
  const { t } = useLanguage();

  return (
    <footer className="bg-secondary border-t mt-16">
      <div className="container py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div>
            <h3 className="font-semibold text-lg mb-4">Induduzo Funeral Home</h3>
            <p className="text-muted-foreground text-base">
              {t("footer_tagline")}
            </p>
          </div>

          <div>
            <h4 className="font-semibold mb-4">{t("footer_quick_links")}</h4>
            <nav className="flex flex-col space-y-2 text-base">
              <NavLink to="/" className="hover:text-primary transition-colors">
                {t("nav_home")}
              </NavLink>
              <NavLink to="/about" className="hover:text-primary transition-colors">
                {t("nav_about")}
              </NavLink>
              <NavLink to="/services" className="hover:text-primary transition-colors">
                {t("nav_services")}
              </NavLink>
              <NavLink to="/contact" className="hover:text-primary transition-colors">
                {t("nav_contact")}
              </NavLink>
              <NavLink to="/join" className="hover:text-primary transition-colors">
                {t("nav_join")}
              </NavLink>
            </nav>
          </div>

          <div>
            <h4 className="font-semibold mb-4">{t("footer_contact_info")}</h4>
            <div className="space-y-3 text-base">
              <a href="tel:0829549241" className="flex items-center hover:text-primary transition-colors">
                <Phone className="h-5 w-5 mr-2" />
                082 954 9241
              </a>
              <a href="mailto:info@induduzofuneralhome.co.za" className="flex items-center hover:text-primary transition-colors">
                <Mail className="h-5 w-5 mr-2" />
                info@induduzofuneralhome.co.za
              </a>
              <div className="flex items-start">
                <MapPin className="h-5 w-5 mr-2 mt-1 flex-shrink-0" />
                <span>Edendale Main Road Kwadaya, Pietermaritzburg 3201</span>
              </div>
            </div>
          </div>
        </div>

        <div className="border-t mt-8 pt-6 text-center text-sm text-muted-foreground">
          <p>© {new Date().getFullYear()} Induduzo Funeral Home. All rights reserved.</p>
          <p className="mt-2">POPIA compliant - Your privacy is important to us.</p>
        </div>
      </div>
    </footer>
  );
};
