import { useState } from "react";
import { useLanguage } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Phone, Mail, MapPin, MessageCircle } from "lucide-react";
import { toast } from "sonner";

export default function Contact() {
  const { t } = useLanguage();
  const [formData, setFormData] = useState({
    name: "",
    phone: "",
    email: "",
    message: "",
    consent: false
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    toast.info(t("form_preview"));
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
                <a href="tel:0829549241" className="text-lg font-semibold text-primary hover:underline">
                  082 954 9241
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
                  href="https://wa.me/27829549241" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="text-lg font-semibold text-[#25D366] hover:underline"
                >
                  082 954 9241
                </a>
                <p className="text-sm text-muted-foreground mt-2">Instant messaging</p>
              </CardContent>
            </Card>

            <Card className="hover:shadow-elevated transition-shadow">
              <CardContent className="p-8 text-center">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-primary/10 rounded-full mb-4">
                  <Mail className="h-8 w-8 text-primary" />
                </div>
                <h3 className="mb-3 text-xl">{t("contact_email")}</h3>
                <a 
                  href="mailto:info@induduzofuneralhome.co.za" 
                  className="text-base font-semibold text-primary hover:underline break-all"
                >
                  info@induduzofuneralhome.co.za
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
                <h2 className="mb-6 text-2xl">Send us a message</h2>
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

                  <Button type="submit" size="lg" className="w-full" disabled>
                    {t("form_submit")}
                  </Button>
                  
                  <p className="text-sm text-center text-muted-foreground">
                    {t("form_preview")}
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
