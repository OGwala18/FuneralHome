import { useState } from "react";
import { useLanguage } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Phone, Mail, MapPin, MessageCircle } from "lucide-react";
import {
  CONTACT_EMAIL,
  CONTACT_EMAIL_LINK,
  CONTACT_PHONE_DISPLAY,
  CONTACT_PHONE_LINK,
  WHATSAPP_URL,
} from "@/lib/contact";

export default function Contact() {
  const { language, t } = useLanguage();
  const [formData, setFormData] = useState({
    name: "",
    phone: "",
    email: "",
    message: "",
    consent: false
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.consent) {
      return;
    }

    const subject = encodeURIComponent(
      language === "en"
        ? `Website enquiry from ${formData.name}`
        : `Umbuzo ovela ku-${formData.name}`,
    );
    const body = encodeURIComponent(
      [
        `${language === "en" ? "Name" : "Igama"}: ${formData.name}`,
        `${language === "en" ? "Phone" : "Ucingo"}: ${formData.phone}`,
        `${language === "en" ? "Email" : "I-imeyili"}: ${formData.email}`,
        "",
        formData.message,
      ].join("\n"),
    );

    window.location.href = `${CONTACT_EMAIL_LINK}?subject=${subject}&body=${body}`;
  };

  return (
    <div className="flex flex-col">
      <section className="bg-secondary/30 py-20">
        <div className="container">
          <div className="max-w-3xl mx-auto text-center">
            <h1 className="mb-6">{t("contact_title")}</h1>
            <p className="text-xl leading-relaxed">
              {t("contact_subtitle")}
            </p>
          </div>
        </div>
      </section>

      <section className="py-20">
        <div className="container">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-16">
            <Card className="hover:shadow-elevated transition-shadow">
              <CardContent className="p-8 text-center">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-primary/10 rounded-full mb-4">
                  <Phone className="h-8 w-8 text-primary" />
                </div>
                <h3 className="mb-3 text-xl">{t("contact_phone")}</h3>
                <a href={CONTACT_PHONE_LINK} className="text-lg font-semibold text-primary hover:underline">
                  {CONTACT_PHONE_DISPLAY}
                </a>
                <p className="text-sm text-muted-foreground mt-2">24/7 {t("cta_call")}</p>
              </CardContent>
            </Card>

            <Card className="hover:shadow-elevated transition-shadow">
              <CardContent className="p-8 text-center">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-[#25D366]/10 rounded-full mb-4">
                  <MessageCircle className="h-8 w-8 text-[#25D366]" />
                </div>
                <h3 className="mb-3 text-xl">{t("contact_whatsapp")}</h3>
                <a 
                  href={WHATSAPP_URL}
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="text-lg font-semibold text-[#25D366] hover:underline"
                >
                  {CONTACT_PHONE_DISPLAY}
                </a>
                <p className="text-sm text-muted-foreground mt-2">{t("contact_instant_messaging")}</p>
              </CardContent>
            </Card>

            <Card className="hover:shadow-elevated transition-shadow">
              <CardContent className="p-8 text-center">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-primary/10 rounded-full mb-4">
                  <Mail className="h-8 w-8 text-primary" />
                </div>
                <h3 className="mb-3 text-xl">{t("contact_email")}</h3>
                <a 
                  href={CONTACT_EMAIL_LINK}
                  className="text-base font-semibold text-primary hover:underline break-all"
                >
                  {CONTACT_EMAIL}
                </a>
              </CardContent>
            </Card>

            <Card className="hover:shadow-elevated transition-shadow">
              <CardContent className="p-8 text-center">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-primary/10 rounded-full mb-4">
                  <MapPin className="h-8 w-8 text-primary" />
                </div>
                <h3 className="mb-3 text-xl">{t("contact_address")}</h3>
                <p className="text-base">
                  Edendale Main Road Kwadaya,<br />
                  Pietermaritzburg 3201
                </p>
              </CardContent>
            </Card>
          </div>

          <div className="max-w-2xl mx-auto">
            <Card>
              <CardContent className="p-8">
                <h2 className="mb-6 text-2xl">{t("contact_form_title")}</h2>
                <form onSubmit={handleSubmit} className="space-y-6">
                  <div>
                    <label htmlFor="name" className="block mb-2 font-medium">
                      {t("form_name")}
                    </label>
                    <Input
                      id="name"
                      value={formData.name}
                      onChange={(e) => setFormData({...formData, name: e.target.value})}
                      required
                      className="text-base"
                    />
                  </div>

                  <div>
                    <label htmlFor="phone" className="block mb-2 font-medium">
                      {t("form_phone")}
                    </label>
                    <Input
                      id="phone"
                      type="tel"
                      value={formData.phone}
                      onChange={(e) => setFormData({...formData, phone: e.target.value})}
                      required
                      className="text-base"
                    />
                  </div>

                  <div>
                    <label htmlFor="email" className="block mb-2 font-medium">
                      {t("form_email")}
                    </label>
                    <Input
                      id="email"
                      type="email"
                      value={formData.email}
                      onChange={(e) => setFormData({...formData, email: e.target.value})}
                      required
                      className="text-base"
                    />
                  </div>

                  <div>
                    <label htmlFor="message" className="block mb-2 font-medium">
                      {t("form_message")}
                    </label>
                    <Textarea
                      id="message"
                      value={formData.message}
                      onChange={(e) => setFormData({...formData, message: e.target.value})}
                      required
                      rows={5}
                      className="text-base"
                    />
                  </div>

                  <div className="flex items-start space-x-2">
                    <Checkbox
                      id="consent"
                      checked={formData.consent}
                      onCheckedChange={(checked) => setFormData({...formData, consent: checked as boolean})}
                      required
                    />
                    <label htmlFor="consent" className="text-sm cursor-pointer">
                      {t("form_consent")}
                    </label>
                  </div>

                  <Button type="submit" size="lg" className="w-full" disabled={!formData.consent}>
                    {t("form_submit")}
                  </Button>
                  
                  <p className="text-sm text-center text-muted-foreground">
                    {t("contact_form_notice")}
                  </p>
                </form>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>
    </div>
  );
}
