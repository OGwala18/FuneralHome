import { Button } from "@/components/ui/button";
import { useLanguage, type Language } from "@/lib/i18n";
import { NavLink } from "@/lib/navigation";
import founderPhoto from "@/assets/founder-themba-njilo.jpg";

/**
 * The founder's story, in the owner's own words (13 Nov 2026).
 *
 * The English is the owner's. The isiZulu was translated for the site on
 * 13 Nov 2026 at the owner's request, for a fluent reader at Induduzo to check;
 * correct it here, in one place.
 */

type Copy = {
  title: string;
  intro: string;
  story: string[];
  closing: string;
  caption: string;
  alt: string;
};

const COPY: Record<Language, Copy> = {
  en: {
    title: "The Man Behind Induduzo",
    intro:
      "Every business has a story, and behind Induduzo Funeral Home is a man who believed " +
      "that every family deserves dignity, care and support during life's most difficult moments.",
    story: [
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
    ],
    closing: "Today, that legacy continues into the next generation.",
    caption: "Mr Themba Njilo, founder of Induduzo Funeral Home",
    alt: "Mr Themba Njilo, founder of Induduzo Funeral Home, smiling at his desk",
  },
  zu: {
    title: "Indoda Engemuva Kwe-Induduzo",
    intro:
      "Lonke ibhizinisi linendaba yalo, futhi ngemuva kwe-Induduzo Funeral Home kukhona indoda " +
      "eyayikholelwa ukuthi yonke imindeni ifanelwe isithunzi, ukunakekelwa nokusekelwa " +
      "ezikhathini ezinzima kakhulu empilweni.",
    story: [
      "Hlangana noMnumzane Themba Njilo, umsunguli we-Induduzo Funeral Home. Ngo-1998, " +
        "ngesikhathi sezinxushunxushu zezombusazwe emphakathini, wasungula i-Induduzo ngombono " +
        "wokuthi imindeni eshonelwe ibe nendawo ethembekile engaphendukela kuyo lapho " +
        "iyidinga kakhulu.",
      "Kodwa ifa lakhe lidlulela ngale kwezinsizakalo zemingcwabo. Ngeminyaka eminingi " +
        "yokweluleka nokufundisa abanye, usizile ekuthuthukiseni abanye abangcwabi kuso sonke " +
        "isifunda saseMidlands, evulela abanye amathuba okwakha amabhizinisi abo. Nge-Thembanjilo " +
        "Foundation, uyaqhubeka nokuxhasa intsha nentuthuko yomphakathi.",
      "KuMnumzane Njilo, ukwakha i-Induduzo bekulokhu kungaphezu nje kokuphatha ibhizinisi. " +
        "Kumayelana nabantu, nomphakathi, nokuqinisekisa ukuthi imindeni ayilokothi ibhekane " +
        "nezikhathi ezinzima iyodwa.",
    ],
    closing: "Namuhla, lelo fa liyaqhubeka esizukulwaneni esilandelayo.",
    caption: "UMnumzane Themba Njilo, umsunguli we-Induduzo Funeral Home",
    alt: "UMnumzane Themba Njilo, umsunguli we-Induduzo Funeral Home, emamatheka etafuleni lakhe",
  },
};

/** The business's own words, the same in both languages. */
const TAGLINE = "Siyazazi izingxaki zakho";

export default function Founder() {
  const { language, t } = useLanguage();
  const copy = COPY[language];

  return (
    <div className="flex flex-col" lang={language}>
      <section className="bg-secondary/30 py-16 md:py-20">
        <div className="container">
          <div className="grid grid-cols-1 items-center gap-10 md:grid-cols-2 md:gap-12">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wider text-primary">
                {t("founder_story")}
              </p>
              <h1 className="mt-3 mb-6">{copy.title}</h1>
              <p className="text-xl leading-relaxed">{copy.intro}</p>
            </div>
            <figure>
              <img
                src={founderPhoto}
                width={960}
                height={640}
                alt={copy.alt}
                className="w-full rounded-lg shadow-medium"
              />
              <figcaption className="mt-3 text-sm text-muted-foreground">{copy.caption}</figcaption>
            </figure>
          </div>
        </div>
      </section>

      <section className="py-16 md:py-20">
        <div className="container">
          <div className="mx-auto max-w-3xl space-y-6 text-lg leading-relaxed">
            {copy.story.map((paragraph) => (
              <p key={paragraph.slice(0, 24)}>{paragraph}</p>
            ))}
            <blockquote className="border-l-4 border-primary pl-6 text-xl italic">
              {copy.closing}
            </blockquote>
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
