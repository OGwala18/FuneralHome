import { MessageCircle } from "lucide-react";
import { WHATSAPP_URL } from "@/lib/contact";
import { useLanguage } from "@/lib/i18n";

export const WhatsAppButton = () => {
  const { t } = useLanguage();

  return (
    <a
      href={WHATSAPP_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="safe-fixed-corner fixed z-50 rounded-full bg-[#25D366] p-3 text-white shadow-elevated transition-transform hover:scale-110 sm:p-4"
      aria-label={t("whatsapp_aria")}
    >
      <MessageCircle className="h-6 w-6" />
    </a>
  );
};
