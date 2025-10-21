import { Phone, MessageCircle, ArrowRight } from "lucide-react";
import { NavLink } from "react-router-dom";
import { useLanguage } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import heroImage from "@/assets/hero-sunrise.jpg";

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

const plans = [
  {
    name_en: "Plan A (Urban)",
    name_zu: "Uhlelo A (Edolobheni)",
    price: "350",
    coverage: "Up to 15 members",
  },
  {
    name_en: "Plan B (Emakhaya)",
    name_zu: "Uhlelo B (Emakhaya)",
    price: "250",
    coverage: "Up to 15 members",
  },
  {
    name_en: "Plan C (Singles/Couples)",
    name_zu: "Uhlelo C (Abangashadile)",
    price: "50",
    coverage: "Individual or couple coverage",
  },
];

export default function Home() {
  const { language, t } = useLanguage();

  return (
    <div className="flex flex-col">
      {/* Hero Section */}
      <section className="relative h-[600px] flex items-center justify-center overflow-hidden">
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
                <a href="tel:0829549241">
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
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto">
            {plans.map((plan, index) => (
              <Card key={index} className={index === 1 ? "border-primary border-2" : ""}>
                <CardContent className="p-8 text-center">
                  <h3 className="mb-4 text-xl">
                    {language === 'en' ? plan.name_en : plan.name_zu}
                  </h3>
                  <div className="mb-4">
                    <span className="text-sm text-muted-foreground uppercase">{t("from")}</span>
                    <div className="text-5xl font-bold text-primary">
                      R{plan.price}
                    </div>
                    <span className="text-muted-foreground">{t("per_month")}</span>
                  </div>
                  <p className="text-sm text-muted-foreground mb-6">{plan.coverage}</p>
                  <Button asChild variant={index === 1 ? "default" : "outline"} className="w-full">
                    <NavLink to="/join">{t("cta_join")}</NavLink>
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
          
          <div className="text-center mt-8">
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
              <h3 className="mb-2">Need immediate assistance?</h3>
              <p className="text-lg opacity-90">We're available 24 hours a day, 7 days a week</p>
            </div>
            <div className="flex gap-4">
              <Button size="lg" variant="secondary" asChild>
                <a href="tel:0829549241">
                  <Phone className="mr-2 h-5 w-5" />
                  082 954 9241
                </a>
              </Button>
              <Button size="lg" variant="secondary" asChild>
                <a href="https://wa.me/27829549241" target="_blank" rel="noopener noreferrer">
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
