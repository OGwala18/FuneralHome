import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { NavLink } from "@/lib/navigation";
import founderPhoto from "@/assets/founder-themba-njilo.jpg";

/**
 * The founder's story, in the owner's own words (13 Nov 2026).
 *
 * The story is in English only, as the owner wrote it. The headings follow the
 * visitor's language; an isiZulu version of the story waits for a fluent
 * reader to write or check it, rather than a machine translation of a tribute.
 */

const INTRO =
  "Every business has a story, and behind Induduzo Funeral Home is a man who believed " +
  "that every family deserves dignity, care and support during life's most difficult moments.";

const STORY = [
  "Meet Mr Themba Njilo, the founder of Induduzo Funeral Home. In 1998, during a time of " +
    "political unrest in the community, he established Induduzo with a vision to give " +
    "grieving families a trusted place to turn to when they needed it most.",
  "But his legacy goes beyond funeral services. Through years of mentorship, he has helped " +
    "develop other funeral directors across the Midlands, creating opportunities for others " +
    "to build businesses of their own. Through the Thembanjilo Foundation, he continues to " +
    "support young people and community development.",
  "For Mr Njilo, building Induduzo has always been about more than running a business. " +
    "It is about people, community and making sure families never have to face difficult " +
    "moments alone.",
];

const CLOSING = "Today, that legacy continues into the next generation.";

const TAGLINE = "Siyazazi izingxaki zakho";

export default function Founder() {
  const { language, t } = useLanguage();
  const en = language === "en";

  return (
    <div className="flex flex-col">
      <section className="bg-secondary/30 py-16 md:py-20">
        <div className="container">
          <div className="grid grid-cols-1 items-center gap-10 md:grid-cols-2 md:gap-12">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wider text-primary">
                {t("founder_story")}
              </p>
              <h1 className="mt-3 mb-6">
                {en ? "The Man Behind Induduzo" : "Umsunguli we-Induduzo"}
              </h1>
              <p className="text-xl leading-relaxed">{INTRO}</p>
            </div>
            <figure>
              <img
                src={founderPhoto}
                width={960}
                height={640}
                alt="Mr Themba Njilo, founder of Induduzo Funeral Home, smiling at his desk"
                className="w-full rounded-lg shadow-medium"
              />
              <figcaption className="mt-3 text-sm text-muted-foreground">
                {en
                  ? "Mr Themba Njilo, founder of Induduzo Funeral Home"
                  : "UMnu Themba Njilo, umsunguli we-Induduzo Funeral Home"}
              </figcaption>
            </figure>
          </div>
        </div>
      </section>

      <section className="py-16 md:py-20">
        <div className="container">
          <div className="mx-auto max-w-3xl space-y-6 text-lg leading-relaxed">
            {!en && (
              <p className="text-base text-muted-foreground" lang="zu">
                Le ndaba itholakala ngesiNgisi kuphela okwamanje.
              </p>
            )}
            <div lang="en" className="space-y-6">
              {STORY.map((paragraph) => (
                <p key={paragraph.slice(0, 24)}>{paragraph}</p>
              ))}
              <blockquote className="border-l-4 border-primary pl-6 text-xl italic">
                {CLOSING}
              </blockquote>
            </div>
            <p className="pt-4 text-center text-2xl font-semibold uppercase tracking-wide text-primary" lang="zu">
              {TAGLINE}
            </p>
            <div className="flex flex-col justify-center gap-3 pt-4 sm:flex-row">
              <Button asChild size="lg">
                <NavLink to="/join">{t("nav_join")}</NavLink>
              </Button>
              <Button asChild size="lg" variant="outline">
                <NavLink to="/contact">{t("nav_contact")}</NavLink>
              </Button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
