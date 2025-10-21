import { useState } from "react";
import { useLanguage } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronUp } from "lucide-react";

export default function Join() {
  const { language, t } = useLanguage();
  const [expandedPlan, setExpandedPlan] = useState<string | null>(null);

  const togglePlan = (planId: string) => {
    setExpandedPlan(expandedPlan === planId ? null : planId);
  };

  return (
    <div className="flex flex-col">
      <section className="bg-secondary/30 py-20">
        <div className="container">
          <div className="max-w-3xl mx-auto text-center">
            <h1 className="mb-6">{t("join_title")}</h1>
            <p className="text-xl leading-relaxed">
              {t("join_subtitle")}
            </p>
          </div>
        </div>
      </section>

      <section className="py-20">
        <div className="container">
          {/* Important Notices */}
          <div className="max-w-4xl mx-auto mb-12 space-y-4">
            <Card className="border-accent bg-accent/5">
              <CardContent className="p-6">
                <p className="text-base font-medium">
                  ⏱ {t("waiting_period")}
                </p>
              </CardContent>
            </Card>
            <Card className="border-accent bg-accent/5">
              <CardContent className="p-6">
                <p className="text-base font-medium">
                  💰 {t("joining_fee")}: R50 for all plans
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Plan A - Urban */}
          <Card className="max-w-4xl mx-auto mb-8">
            <CardContent className="p-8">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h2 className="text-3xl mb-2">{t("plan_a_title")}</h2>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold text-primary">R350</span>
                    <span className="text-lg text-muted-foreground">{t("per_month")}</span>
                  </div>
                  <p className="text-muted-foreground mt-2">
                    {language === 'en' 
                      ? 'Up to 15 family members • No age limits' 
                      : 'Kuya ku-15 amalungu omndeni • Ayikho imikhawulo yeminyaka'}
                  </p>
                </div>
                <Button 
                  variant="outline" 
                  onClick={() => togglePlan('plan-a')}
                  className="ml-4"
                >
                  {expandedPlan === 'plan-a' ? (
                    <><ChevronUp className="mr-2 h-4 w-4" /> {t("hide_inclusions")}</>
                  ) : (
                    <><ChevronDown className="mr-2 h-4 w-4" /> {t("view_inclusions")}</>
                  )}
                </Button>
              </div>

              {expandedPlan === 'plan-a' && (
                <div className="border-t pt-6">
                  <h4 className="font-semibold mb-4 text-lg">
                    {language === 'en' ? 'Plan Inclusions:' : 'Okufakiwe Kohlelweni:'}
                  </h4>
                  <ul className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {[
                      language === 'en' ? 'Casket' : 'Ibhokisi',
                      language === 'en' ? 'Isiphambano (Cross)' : 'Isiphambano',
                      language === 'en' ? 'Amakhaza (Funeral equipment)' : 'Amakhaza',
                      language === 'en' ? 'Tent & Chairs (Home & Cemetery)' : 'Itende Nezitulo (Ekhaya Nasemathuneni)',
                      language === 'en' ? 'Photo Frame' : 'Isikhungo Sesithombe',
                      language === 'en' ? 'Programme' : 'Uhlelo',
                      language === 'en' ? 'Gown' : 'Ingubo',
                      language === 'en' ? 'Hearse and family car' : 'I-hearse nemoto yomndeni',
                      language === 'en' ? 'Udokotela (Doctor fees)' : 'Udokotela',
                      language === 'en' ? 'Grave at Ethembeni Cemetery' : 'Umgodi e-Ethembeni',
                      language === 'en' ? 'Cemetery Equipment' : 'Izinto Zemathuna',
                    ].map((item, i) => (
                      <li key={i} className="flex items-start">
                        <span className="inline-block w-2 h-2 bg-primary rounded-full mt-2 mr-3 flex-shrink-0"></span>
                        <span className="text-base">{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Plan B - Emakhaya */}
          <Card className="max-w-4xl mx-auto mb-8">
            <CardContent className="p-8">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h2 className="text-3xl mb-2">{t("plan_b_title")}</h2>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold text-primary">R250</span>
                    <span className="text-lg text-muted-foreground">{t("per_month")}</span>
                  </div>
                  <p className="text-muted-foreground mt-2">
                    {language === 'en' 
                      ? 'Up to 15 family members • No age limits' 
                      : 'Kuya ku-15 amalungu omndeni • Ayikho imikhawulo yeminyaka'}
                  </p>
                </div>
                <Button 
                  variant="outline" 
                  onClick={() => togglePlan('plan-b')}
                  className="ml-4"
                >
                  {expandedPlan === 'plan-b' ? (
                    <><ChevronUp className="mr-2 h-4 w-4" /> {t("hide_inclusions")}</>
                  ) : (
                    <><ChevronDown className="mr-2 h-4 w-4" /> {t("view_inclusions")}</>
                  )}
                </Button>
              </div>

              {expandedPlan === 'plan-b' && (
                <div className="border-t pt-6">
                  <h4 className="font-semibold mb-4 text-lg">
                    {language === 'en' ? 'Plan Inclusions:' : 'Okufakiwe Kohlelweni:'}
                  </h4>
                  <ul className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {[
                      language === 'en' ? 'Removal' : 'Ukususwa',
                      language === 'en' ? 'Amakhaza/Storage' : 'Amakhaza/Ukugcinwa',
                      language === 'en' ? 'Udokotela' : 'Udokotela',
                      language === 'en' ? 'Casket' : 'Ibhokisi',
                      language === 'en' ? 'Isiphambano' : 'Isiphambano',
                      language === 'en' ? 'Gown' : 'Ingubo',
                      language === 'en' ? 'Hearse and family car' : 'I-hearse nemoto yomndeni',
                      language === 'en' ? 'Tent (2 poles) & Chairs (50)' : 'Itende (Izinsika ezi-2) Nezitulo (50)',
                      language === 'en' ? 'Photo Frame (A3)' : 'Isikhungo Sesithombe (A3)',
                    ].map((item, i) => (
                      <li key={i} className="flex items-start">
                        <span className="inline-block w-2 h-2 bg-primary rounded-full mt-2 mr-3 flex-shrink-0"></span>
                        <span className="text-base">{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Plan C - Singles/Couples */}
          <Card className="max-w-4xl mx-auto mb-8">
            <CardContent className="p-8">
              <div className="mb-6">
                <h2 className="text-3xl mb-2">{t("plan_c_title")}</h2>
                <p className="text-muted-foreground">
                  {language === 'en' 
                    ? 'Individual or couple coverage with flexible options' 
                    : 'Ukumbozwa komuntu oyedwa noma izithandani ngezinketho eziguquguqukayo'}
                </p>
              </div>

              <div className="space-y-6">
                <div>
                  <h3 className="font-semibold text-xl mb-4">
                    {language === 'en' ? 'Single Member' : 'Ilungu Elilodwa'}
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full border">
                      <thead className="bg-secondary">
                        <tr>
                          <th className="p-3 text-left">{language === 'en' ? 'Age Group' : 'Iqembu Leminyaka'}</th>
                          <th className="p-3 text-left">{language === 'en' ? 'Flat Lid' : 'I-Flat Lid'}</th>
                          <th className="p-3 text-left">{language === 'en' ? 'Casket' : 'Ibhokisi'}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-t">
                          <td className="p-3">21-45</td>
                          <td className="p-3 font-semibold">R50</td>
                          <td className="p-3 font-semibold">R150</td>
                        </tr>
                        <tr className="border-t">
                          <td className="p-3">46-59</td>
                          <td className="p-3 font-semibold">R60</td>
                          <td className="p-3 font-semibold">R180</td>
                        </tr>
                        <tr className="border-t">
                          <td className="p-3">60-75</td>
                          <td className="p-3 font-semibold">R80</td>
                          <td className="p-3 font-semibold">R200</td>
                        </tr>
                        <tr className="border-t">
                          <td className="p-3">76-85</td>
                          <td className="p-3 font-semibold">R120</td>
                          <td className="p-3 font-semibold">R250</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold text-xl mb-4">
                    {language === 'en' ? 'Couple (with children under 21)' : 'Izithandani (nezingane ezingaphansi kweminyaka engu-21)'}
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full border">
                      <thead className="bg-secondary">
                        <tr>
                          <th className="p-3 text-left">{language === 'en' ? 'Age Group' : 'Iqembu Leminyaka'}</th>
                          <th className="p-3 text-left">{language === 'en' ? 'Flat Lid Package' : 'Iphakethe Le-Flat Lid'}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-t">
                          <td className="p-3">21-45</td>
                          <td className="p-3 font-semibold">R100</td>
                        </tr>
                        <tr className="border-t">
                          <td className="p-3">46-59</td>
                          <td className="p-3 font-semibold">R200</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <Button 
                  variant="outline" 
                  onClick={() => togglePlan('plan-c')}
                  className="w-full"
                >
                  {expandedPlan === 'plan-c' ? (
                    <><ChevronUp className="mr-2 h-4 w-4" /> {t("hide_inclusions")}</>
                  ) : (
                    <><ChevronDown className="mr-2 h-4 w-4" /> {t("view_inclusions")}</>
                  )}
                </Button>

                {expandedPlan === 'plan-c' && (
                  <div className="border-t pt-6">
                    <h4 className="font-semibold mb-4 text-lg">
                      {language === 'en' ? 'Plan Inclusions (Emakhaya):' : 'Okufakiwe Kohlelweni (Emakhaya):'}
                    </h4>
                    <ul className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {[
                        language === 'en' ? 'Removal' : 'Ukususwa',
                        language === 'en' ? 'Amakhaza/Storage' : 'Amakhaza/Ukugcinwa',
                        language === 'en' ? 'Udokotela' : 'Udokotela',
                        language === 'en' ? 'Flat lid or Casket (based on selection)' : 'I-Flat lid noma Ibhokisi (ngokuya ngokukhethwayo)',
                        language === 'en' ? 'Isiphambano' : 'Isiphambano',
                        language === 'en' ? 'Gown' : 'Ingubo',
                        language === 'en' ? 'Hearse' : 'I-hearse',
                        language === 'en' ? 'Tent (2 poles) & Chairs (50)' : 'Itende (Izinsika ezi-2) Nezitulo (50)',
                      ].map((item, i) => (
                        <li key={i} className="flex items-start">
                          <span className="inline-block w-2 h-2 bg-primary rounded-full mt-2 mr-3 flex-shrink-0"></span>
                          <span className="text-base">{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Additional Plan - Ikhishi */}
          <Card className="max-w-4xl mx-auto mb-8 border-accent">
            <CardContent className="p-8">
              <div className="mb-6">
                <h2 className="text-3xl mb-2">Ikhishi</h2>
                <div className="flex items-baseline gap-2">
                  <span className="text-4xl font-bold text-primary">R50</span>
                  <span className="text-lg text-muted-foreground">{t("per_month")}</span>
                </div>
              </div>

              <div className="space-y-4 text-base">
                <p>
                  <strong>{language === 'en' ? 'Once-off fee:' : 'Imali Kanye Kuphela:'}</strong>
                </p>
                <ul className="ml-6 space-y-2">
                  <li>• R400 – {language === 'en' ? 'Casket plans' : 'Izinhlelo zebhokisi'}</li>
                  <li>• R300 – {language === 'en' ? 'Flat lid plans' : 'Izinhlelo ze-flat lid'}</li>
                </ul>

                <p>
                  <strong>{language === 'en' ? 'Coverage:' : 'Ukumbozwa:'}</strong>
                </p>
                <ul className="ml-6 space-y-2">
                  <li>• R1,000 {language === 'en' ? 'for person under 21 years' : 'kumuntu ongaphansi kweminyaka engu-21'}</li>
                  <li>• R2,000 {language === 'en' ? 'for person above 21 years' : 'kumuntu ongaphezu kweminyaka engu-21'}</li>
                </ul>

                <p className="text-muted-foreground">
                  {t("waiting_period")}
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Call to Action */}
          <div className="max-w-4xl mx-auto text-center mt-12">
            <Card className="bg-primary text-primary-foreground">
              <CardContent className="p-8">
                <h3 className="text-2xl mb-4">
                  {language === 'en' 
                    ? 'Ready to join a plan?' 
                    : 'Ulungele ukujoyina uhlelo?'}
                </h3>
                <p className="text-lg mb-6 opacity-90">
                  {language === 'en' 
                    ? 'Contact us today to get started or for more information' 
                    : 'Xhumana nathi namuhla ukuze uqale noma ukuze uthole ulwazi olwengeziwe'}
                </p>
                <div className="flex flex-wrap gap-4 justify-center">
                  <Button size="lg" variant="secondary" asChild>
                    <a href="tel:0829549241">
                      {t("cta_call")}
                    </a>
                  </Button>
                  <Button size="lg" variant="secondary" asChild>
                    <a href="https://wa.me/27829549241" target="_blank" rel="noopener noreferrer">
                      WhatsApp
                    </a>
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>
    </div>
  );
}
