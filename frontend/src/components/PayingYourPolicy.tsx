import { Card, CardContent } from "@/components/ui/card";
import { useLanguage } from "@/lib/i18n";
import { BANK_DETAILS, PROOF_OF_PAYMENT_WHATSAPP } from "@/lib/banking";
import { CONTACT_EMAIL, CONTACT_EMAIL_LINK } from "@/lib/contact";
import { Landmark, ShieldAlert } from "lucide-react";

/**
 * "Paying your policy?": the official account, how to send proof of payment,
 * and the warning that matters most: never pay into different details.
 * Mirrors the office's flyer. The values live in lib/banking.ts only.
 */
export function PayingYourPolicy({ className = "" }: { className?: string }) {
  const { language } = useLanguage();
  const en = language === "en";

  const rows: [string, string][] = [
    [en ? "Bank" : "Ibhange", BANK_DETAILS.bank],
    [en ? "Account name" : "Igama le-akhawunti", BANK_DETAILS.accountName],
    [en ? "Account type" : "Uhlobo lwe-akhawunti", BANK_DETAILS.accountType],
    [en ? "Branch code" : "Ikhodi yegatsha", BANK_DETAILS.branchCode],
    [en ? "Account number" : "Inombolo ye-akhawunti", BANK_DETAILS.accountNumber],
    [en ? "Reference" : "Isithenjwa", en ? "Your policy number" : "Inombolo yepolisi yakho"],
  ];

  return (
    <Card className={className}>
      <CardContent className="p-6 md:p-8">
        <div className="mb-5 flex items-center gap-3">
          <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <Landmark className="h-6 w-6 text-primary" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-2xl">{en ? "Paying your policy?" : "Ukhokha ipolisi yakho?"}</h2>
            <p className="text-muted-foreground">
              {en ? "Please use our official banking details." : "Sicela usebenzise imininingwane yethu esemthethweni yebhange."}
            </p>
          </div>
        </div>

        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 rounded-lg border p-4 sm:grid-cols-[auto_1fr]">
          {rows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt>
              <dd className="mb-2 font-semibold sm:mb-0">{value}</dd>
            </div>
          ))}
        </dl>

        <ol className="mt-5 list-decimal space-y-2 pl-5">
          <li>
            {en ? "Send your proof of payment on WhatsApp " : "Thumela ubufakazi bokukhokha ku-WhatsApp "}
            <a href={PROOF_OF_PAYMENT_WHATSAPP.link} target="_blank" rel="noopener noreferrer"
               className="font-semibold text-primary hover:underline">
              {PROOF_OF_PAYMENT_WHATSAPP.display}
            </a>
            {en ? " or to " : " noma ku-"}
            <a href={CONTACT_EMAIL_LINK} className="font-semibold text-primary hover:underline">
              {CONTACT_EMAIL.toLowerCase()}
            </a>
            .
          </li>
          <li>{en ? "Keep your proof of payment for your own records." : "Gcina ubufakazi bokukhokha kwakho."}</li>
        </ol>

        <div className="mt-5 flex gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4" role="note">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden="true" />
          <p>
            <strong>
              {en ? "Received different banking details? Do not pay." : "Uthole eminye imininingwane yebhange? Ungakhokhi."}
            </strong>{" "}
            {en
              ? "Contact us first. We will never change our account by SMS, WhatsApp or email."
              : "Xhumana nathi kuqala. Ngeke sishintshe i-akhawunti yethu nge-SMS, i-WhatsApp noma i-imeyili."}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
