import { useLanguage } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/card";
import { Heart, Award, Lightbulb, CheckCircle } from "lucide-react";
import familyImage from "@/assets/family-together.jpg";
import valuesImage from "@/assets/about-values.jpg";

const values = [
  {
    icon: Heart,
    title_en: "Customer First",
    title_zu: "Ikhasimende Lokuqala",
    desc_en: "Your needs and comfort guide everything we do",
    desc_zu: "Izidingo zakho nokunethezeka kwakho kuholela konke esikwenzayo",
  },
  {
    icon: CheckCircle,
    title_en: "Reliability",
    title_zu: "Ukwethembeka",
    desc_en: "Dependable service when you need it most",
    desc_zu: "Insizakalo ethembekile lapho uyidinga kakhulu",
  },
  {
    icon: Award,
    title_en: "Excellence",
    title_zu: "Ubuhle",
    desc_en: "Committed to the highest standards of care",
    desc_zu: "Sizinikele emazingeni aphezulu okunakekelwa",
  },
  {
    icon: Lightbulb,
    title_en: "Innovation",
    title_zu: "Ukusungula",
    desc_en: "Modern solutions with traditional respect",
    desc_zu: "Izixazululo zesimanje ezinenhlonipho yendabuko",
  },
];

export default function About() {
  const { language, t } = useLanguage();

  return (
    <div className="flex flex-col">
      {/* Hero */}
      <section className="bg-secondary/30 py-20">
        <div className="container">
          <div className="max-w-3xl mx-auto text-center">
            <h1 className="mb-6">{t("about_title")}</h1>
            <p className="text-xl leading-relaxed">
              {t("about_intro")}
            </p>
            <p className="text-lg text-muted-foreground mt-6">
              {t("about_since")}
            </p>
          </div>
        </div>
      </section>

      {/* Vision & Mission */}
      <section className="py-20">
        <div className="container">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-12 items-center">
            <div>
              <img 
                src={familyImage} 
                alt="Induduzo family values" 
                className="rounded-lg shadow-medium w-full"
              />
            </div>
            
            <div className="space-y-8">
              <div>
                <h2 className="mb-4 text-3xl">Our Story & Vision</h2>
                <p className="text-xl leading-relaxed">
                  Induduzo Care was founded to serve families with dignity, respect, and cultural understanding. Our vision lives in daily actions — from careful planning to the warmth we extend to every family we meet.
                </p>
                <p className="text-lg text-muted-foreground mt-4">
                  Learn more about our founder's journey on the <a href="/founder" className="text-primary hover:underline">Founder</a> page.
                </p>
              </div>
              
              <div>
                <h2 className="mb-4 text-3xl">{t("our_mission")}</h2>
                <p className="text-xl leading-relaxed">{t("mission_text")}</p>
              </div>
              
              <div className="grid grid-cols-2 gap-6 pt-8">
                <div className="text-center">
                  <div className="text-4xl font-bold text-primary mb-2">1998</div>
                  <div className="text-muted-foreground">
                    {language === 'en' ? 'Since' : 'Kusukela'}
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-4xl font-bold text-primary mb-2">3000+</div>
                  <div className="text-muted-foreground">
                    {language === 'en' ? 'Funerals' : 'Imingcwabo'}
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-4xl font-bold text-primary mb-2">1300+</div>
                  <div className="text-muted-foreground">
                    {language === 'en' ? 'Members' : 'Amalungu'}
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-4xl font-bold text-primary mb-2">24/7</div>
                  <div className="text-muted-foreground">
                    {language === 'en' ? 'Available' : 'Siyatholakala'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Our Values */}
      <section 
        className="py-20 bg-cover bg-center relative"
        style={{ backgroundImage: `url(${valuesImage})` }}
      >
        <div className="absolute inset-0 bg-black/60"></div>
        <div className="container relative z-10">
          <div className="text-center mb-12">
            <h2 className="mb-4 text-white">{t("our_values")}</h2>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {values.map((value, index) => {
              const Icon = value.icon;
              return (
                <Card key={index} className="bg-white/95 hover:bg-white transition-colors">
                  <CardContent className="p-8 text-center">
                    <div className="inline-flex items-center justify-center w-16 h-16 bg-primary/10 rounded-full mb-4">
                      <Icon className="h-8 w-8 text-primary" />
                    </div>
                    <h3 className="mb-3 text-xl">
                      {language === 'en' ? value.title_en : value.title_zu}
                    </h3>
                    <p className="text-muted-foreground">
                      {language === 'en' ? value.desc_en : value.desc_zu}
                    </p>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      </section>
    </div>
  );
}
