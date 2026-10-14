import { useLanguage } from "@/lib/i18n";
import { NavLink } from "@/lib/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Check, Clock, Heart, MessageCircle, Phone, UserPlus, Users, Wallet } from "lucide-react";
import { CONTACT_PHONE_LINK, WHATSAPP_URL } from "@/lib/contact";
import { GUARANTEED_PAYOUTS, PLANS, PLAN_TERMS, type Plan } from "@/data/plans";

const TERM_ICONS = {
  clock: Clock,
  wallet: Wallet,
  users: Users,
  heart: Heart,
} as const;

export default function Join() {
  const { language, t } = useLanguage();

  return (
    <div className="flex flex-col">
      {/* Hero */}
      <section className="bg-navy py-16 text-white md:py-20">
        <div className="container">
          <div className="mx-auto max-w-3xl text-center">
            <h1 className="mb-6 text-white">{t("join_title")}</h1>
            <p className="mb-8 text-lg leading-relaxed text-white/85 md:text-xl">
              {t("join_subtitle")}
            </p>

            {/* Primary action. Sits above the plan detail so someone who already
                knows what they want never has to scroll past four plans to act. */}
            <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Button size="lg" asChild>
                <NavLink to="/register">
                  <UserPlus className="mr-2 h-5 w-5" aria-hidden="true" />
                  {t("cta_register")}
                </NavLink>
              </Button>
              <Button
                size="lg"
                variant="outline"
                className="border-white bg-white/10 text-white hover:bg-white hover:text-navy"
                asChild
              >
                <a href={CONTACT_PHONE_LINK}>
                  <Phone className="mr-2 h-5 w-5" aria-hidden="true" />
                  {t("cta_call")}
                </a>
              </Button>
            </div>
            <p className="mt-4 text-sm text-white/70">{t("register_reassurance")}</p>
          </div>
        </div>
      </section>

      {/* Flyer banner */}
      <div className="bg-accent py-3">
        <div className="container">
          <p className="text-center text-sm font-bold uppercase tracking-[0.12em] text-navy sm:text-base">
            {language === "en"
              ? "Dignified funeral cover, built for Midlands families"
              : "Ukumbozwa komngcwabo okunesithunzi, kwakhelwe imindeni yase-Midlands"}
          </p>
        </div>
      </div>

      {/* Guaranteed payouts */}
      <section className="py-14">
        <div className="container">
          <h2 className="mb-8 text-center text-2xl md:text-3xl">{t("payouts_title")}</h2>
          <div className="mx-auto grid max-w-3xl grid-cols-1 gap-5 sm:grid-cols-2">
            {GUARANTEED_PAYOUTS.map((payout) => (
              <div
                key={payout.amount}
                className="rounded-lg border border-payout-foreground/25 bg-payout px-6 py-7 text-center text-payout-foreground"
              >
                <div className="text-4xl font-bold md:text-5xl">{payout.amount}</div>
                <p className="mt-2 text-sm">{payout.label[language]}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Comparison table — flyer layout, desktop only (cards below carry the same detail) */}
      <section className="hidden pb-14 lg:block">
        <div className="container">
          <div className="mx-auto max-w-5xl">
            <h2 className="mb-2 text-center text-2xl md:text-3xl">{t("compare_title")}</h2>
            <p className="mb-8 text-center text-muted-foreground">{t("compare_note")}</p>

            <div className="overflow-hidden rounded-lg border">
              <table className="w-full text-left">
                <thead className="bg-navy text-white">
                  <tr>
                    <th className="p-4 font-semibold">{t("th_plan")}</th>
                    <th className="p-4 font-semibold">{t("th_coverage")}</th>
                    <th className="p-4 font-semibold">{t("th_price")}</th>
                    <th className="p-4 font-semibold">{t("th_included")}</th>
                  </tr>
                </thead>
                <tbody>
                  {PLANS.map((plan, index) => (
                    <tr
                      key={plan.id}
                      className={index % 2 === 0 ? "bg-secondary/40" : "bg-background"}
                    >
                      <td className="p-4 align-top">
                        <a href={`#${plan.id}`} className="font-semibold text-primary hover:underline">
                          {plan.name[language]}
                        </a>
                      </td>
                      <td className="p-4 align-top text-base">{plan.coverage[language]}</td>
                      <td className="p-4 align-top">
                        <span className="font-semibold">
                          {plan.priceFrom ? `${t("from")} ` : ""}
                          {plan.price}
                        </span>{" "}
                        <span className="text-muted-foreground">{plan.period[language]}</span>
                        {plan.priceAlt && (
                          <div className="text-sm text-muted-foreground">
                            {plan.priceAlt[language]}
                          </div>
                        )}
                      </td>
                      <td className="p-4 align-top text-base leading-relaxed">
                        {plan.summary[language]}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      {/* Plan detail cards */}
      <section className="pb-14">
        <div className="container space-y-8">
          {PLANS.map((plan) => (
            <PlanCard key={plan.id} plan={plan} language={language} t={t} />
          ))}
        </div>
      </section>

      {/* Terms that apply to every plan */}
      <section className="bg-navy py-14 text-white">
        <div className="container">
          <div className="mx-auto max-w-4xl">
            <h2 className="mb-8 text-center text-2xl text-white md:text-3xl">
              {t("plan_terms_title")}
            </h2>
            <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              {PLAN_TERMS.map((term) => {
                const Icon = TERM_ICONS[term.icon];
                return (
                  <li key={term.icon} className="flex items-start gap-4">
                    <span className="mt-0.5 inline-flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-accent/15">
                      <Icon className="h-5 w-5 text-accent" />
                    </span>
                    <span className="text-base leading-relaxed text-white/90">
                      {term.text[language]}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </section>

      {/* Call to action */}
      <section className="py-14">
        <div className="container">
          <Card className="mx-auto max-w-4xl border-transparent bg-band text-band-foreground">
            <CardContent className="p-6 text-center sm:p-10">
              <h3 className="mb-4 text-2xl md:text-3xl">{t("ready_title")}</h3>
              <p className="mb-8 text-lg opacity-90">{t("ready_text")}</p>
              <div className="flex flex-wrap justify-center gap-4">
                <Button size="lg" variant="secondary" asChild>
                  <NavLink to="/register">
                    <UserPlus className="mr-2 h-5 w-5" aria-hidden="true" />
                    {t("cta_register")}
                  </NavLink>
                </Button>
                <Button size="lg" variant="secondary" asChild>
                  <a href={CONTACT_PHONE_LINK}>
                    <Phone className="mr-2 h-5 w-5" aria-hidden="true" />
                    {t("cta_call")}
                  </a>
                </Button>
                <Button size="lg" variant="secondary" asChild>
                  <a href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer">
                    <MessageCircle className="mr-2 h-5 w-5" aria-hidden="true" />
                    WhatsApp
                  </a>
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}

interface PlanCardProps {
  plan: Plan;
  language: "en" | "zu";
  t: (key: string) => string;
}

function PlanCard({ plan, language, t }: PlanCardProps) {
  return (
    <Card
      id={plan.id}
      className={`mx-auto max-w-4xl scroll-mt-24 overflow-hidden ${
        plan.featured ? "border-2 border-primary" : ""
      }`}
    >
      {/* Plan header — the flyer's cream body, with gold kept as a rule rather
          than as text. Gold on cream is a print luxury that does not survive a
          contrast check on screen, so the price carries the brand colour. */}
      <div className="border-b-2 border-accent bg-parchment px-5 py-6 sm:px-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              {plan.coverage[language]}
            </span>
            <h2 className="mt-1 text-3xl">{plan.name[language]}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{plan.members[language]}</p>
          </div>

          <div className="sm:text-right">
            <div className="flex items-baseline gap-2 sm:justify-end">
              {plan.priceFrom && (
                <span className="text-sm uppercase tracking-wide text-muted-foreground">
                  {t("from")}
                </span>
              )}
              <span className="text-4xl font-bold text-primary">{plan.price}</span>
              <span className="text-lg text-muted-foreground">{plan.period[language]}</span>
            </div>
            {plan.priceAlt && (
              <p className="mt-1 text-sm text-muted-foreground">{plan.priceAlt[language]}</p>
            )}
          </div>
        </div>
      </div>

      <CardContent className="p-5 sm:p-8">
        <p className="mb-6 text-base leading-relaxed text-muted-foreground">
          {plan.summary[language]}
        </p>

        {plan.tables?.map((table) => (
          <div key={table.title.en} className="mb-8">
            <h3 className="mb-1 text-xl font-semibold">{table.title[language]}</h3>
            {table.note && (
              <p className="mb-3 text-sm text-muted-foreground">{table.note[language]}</p>
            )}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[320px] border text-left">
                <thead className="bg-secondary">
                  <tr>
                    {table.columns.map((column) => (
                      <th key={column.en} className="p-3 font-semibold">
                        {column[language]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((row) => (
                    <tr key={row[0]} className="border-t">
                      {row.map((cell, cellIndex) => (
                        <td
                          key={cell}
                          className={cellIndex === 0 ? "p-3" : "p-3 font-semibold text-primary"}
                        >
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}

        <div className="border-t pt-6">
          <h3 className="mb-4 text-lg font-semibold">{t("plan_inclusions")}</h3>
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {plan.inclusions.map((item) => (
              <li key={item.en} className="flex items-start gap-3">
                <span className="mt-1 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <Check className="h-3 w-3 text-primary" />
                </span>
                <span className="text-base">{item[language]}</span>
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}
