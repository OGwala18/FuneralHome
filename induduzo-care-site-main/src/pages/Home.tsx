import { Phone, MessageCircle, ArrowRight } from "lucide-react";
import { NavLink } from "@/lib/navigation";
import { useLanguage } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import heroImage from "@/assets/hero-sunrise.jpg";
import {
  CONTACT_PHONE_DISPLAY,
  CONTACT_PHONE_LINK,
  WHATSAPP_URL,
} from "@/lib/contact";
import { GUARANTEED_PAYOUTS, PLANS } from "@/data/plans";

const services = [
  {
    title_en: "Funeral Services",
    title_zu: "Izinsizakalo Zomngcwabo",
    desc_en: "Complete dignified funeral arrangements",
    desc_zu: "Ukuhlelwa okugcwele komngcwabo onesihlonipho",
  },
  {
    title_en: "Funeral Insurance",
    title_zu: "Umshwalense Womngcwabo",
    desc_en: "Affordable coverage for your peace of mind",
    desc_zu: "Ukumbozwa ongakwazi ukukhokhela ukuthula kwakho",
  },
  {
    title_en: "Repatriations",
    title_zu: "Ukubuyiswa Kwezidumbu",
    desc_en: "Safe return of loved ones from afar",
    desc_zu: "Ukubuyiswa okuphephile kwabathandekayo abakude",
  },
  {
    title_en: "Pre-Planning",
    title_zu: "Ukuhlela Ngaphambili",
    desc_en: "Plan ahead with care and confidence",
    desc_zu: "Hlela ngaphambili ngokunakekelwa nokuzethemba",
  },
  {
    title_en: "Exhumations",
    title_zu: "Ukugedlwa Kwamathuna",
    desc_en: "Professional and respectful exhumation services",
    desc_zu: "Izinsizakalo zokugeda amathuna ezinobuchwepheshe nezihloniphekile",
  },
  {
    title_en: "Caskets",
    title_zu: "Amabhokisi Abafileyo",
    desc_en: "Quality caskets and funeral products",
    desc_zu: "Amabhokisi abafileyo nezikhungo zomngcwabo ezisezingeni eliphezulu",
  },
];

export default function Home() {
  const { language, t } = useLanguage();

  return (
    <div className="flex flex-col">
      {/* Hero Section */}
      <section className="relative flex min-h-[560px] items-center justify-center overflow-hidden py-16 md:h-[600px] md:py-0">
        <div 
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: `url(${heroImage})` }}
        >
          <div className="absolute inset-0 bg-gradient-to-r from-black/70 via-black/50 to-transparent"></div>
        </div>
        
        <div className="relative container z-10 text-white">
          <div className="max-w-2xl">
            <h1 className="mb-6">{t("hero_title")}</h1>
            <p className="text-xl mb-8 leading-relaxed">{t("hero_subtitle")}</p>
            
            <div className="flex flex-wrap gap-4">
              <Button size="lg" asChild>
                <a href={CONTACT_PHONE_LINK}>
                  <Phone className="mr-2 h-5 w-5" />
                  {t("cta_call")}
                </a>
              </Button>
              
              <Button size="lg" variant="secondary" asChild>
                <NavLink to="/services">
                  {t("cta_services")}
                  <ArrowRight className="ml-2 h-5 w-5" />
                </NavLink>
              </Button>
              
              <Button size="lg" variant="outline" className="bg-white/10 text-white border-white hover:bg-white hover:text-foreground" asChild>
                <NavLink to="/join">{t("cta_join")}</NavLink>
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* Services Overview */}
      <section className="py-20 bg-secondary/30">
        <div className="container">
          <div className="text-center mb-12">
            <h2 className="mb-4">{t("services_title")}</h2>
            <p className="text-xl text-muted-foreground">{t("services_subtitle")}</p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {services.map((service, index) => (
              <Card key={index} className="hover:shadow-elevated transition-shadow cursor-pointer group">
                <CardContent className="p-8">
                  <h3 className="mb-3 text-2xl group-hover:text-primary transition-colors">
                    {language === 'en' ? service.title_en : service.title_zu}
                  </h3>
                  <p className="text-muted-foreground mb-4">
                    {language === 'en' ? service.desc_en : service.desc_zu}
                  </p>
                  <NavLink to="/services" className="text-primary font-semibold inline-flex items-center group-hover:gap-2 transition-all">
                    {t("learn_more")}
                    <ArrowRight className="ml-1 h-4 w-4 group-hover:translate-x-1 transition-transform" />
                  </NavLink>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Plans Preview */}
      <section className="py-20">
        <div className="container">
          <div className="text-center mb-12">
            <h2 className="mb-4">{t("plans_title")}</h2>
            <p className="text-xl text-muted-foreground">{t("plans_subtitle")}</p>
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 max-w-6xl mx-auto">
            {PLANS.map((plan) => (
              <Card
                key={plan.id}
                className={`flex flex-col ${plan.featured ? "border-primary border-2" : ""}`}
              >
                <CardContent className="flex flex-1 flex-col p-6 text-center">
                  <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                    {plan.coverage[language]}
                  </span>
                  <h3 className="mb-4 mt-1 text-xl">{plan.name[language]}</h3>
                  <div className="mb-4">
                    {plan.priceFrom && (
                      <span className="text-sm text-muted-foreground uppercase">{t("from")}</span>
                    )}
                    <div className="text-4xl font-bold text-primary">{plan.price}</div>
                    <span className="text-muted-foreground">{plan.period[language]}</span>
                    {plan.priceAlt && (
                      <p className="mt-1 text-xs text-muted-foreground">{plan.priceAlt[language]}</p>
                    )}
                  </div>
                  <p className="mb-6 flex-1 text-sm text-muted-foreground">
                    {plan.summary[language]}
                  </p>
                  <Button asChild variant={plan.featured ? "default" : "outline"} className="w-full">
                    <NavLink to="/join">{t("cta_join")}</NavLink>
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Guaranteed payouts — apply to every plan */}
          <div className="mx-auto mt-10 max-w-3xl">
            <p className="mb-4 text-center text-sm font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              {t("payouts_title")}
            </p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {GUARANTEED_PAYOUTS.map((payout) => (
                <div
                  key={payout.amount}
                  className="rounded-lg border-2 border-accent bg-accent/5 px-5 py-5 text-center"
                >
                  <div className="text-3xl font-bold text-primary">{payout.amount}</div>
                  <p className="mt-1 text-sm text-muted-foreground">{payout.label[language]}</p>
                </div>
              ))}
            </div>
          </div>

          <p className="mt-8 text-center text-base font-medium">
            {t("all_names_welcome")}
          </p>

          <div className="text-center mt-6">
            <Button asChild size="lg" variant="outline">
              <NavLink to="/join">
                {t("compare_plans")}
                <ArrowRight className="ml-2 h-5 w-5" />
              </NavLink>
            </Button>
          </div>
        </div>
      </section>

      {/* Immediate Help CTA */}
      <section className="bg-primary text-primary-foreground py-12">
        <div className="container">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div>
              <h3 className="mb-2">{t("immediate_help_title")}</h3>
              <p className="text-lg opacity-90">{t("immediate_help_text")}</p>
            </div>
            <div className="flex flex-wrap justify-center gap-4 md:justify-end">
              <Button size="lg" variant="secondary" asChild>
                <a href={CONTACT_PHONE_LINK}>
                  <Phone className="mr-2 h-5 w-5" />
                  {CONTACT_PHONE_DISPLAY}
                </a>
              </Button>
              <Button size="lg" variant="secondary" asChild>
                <a href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer">
                  <MessageCircle className="mr-2 h-5 w-5" />
                  WhatsApp
                </a>
              </Button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
