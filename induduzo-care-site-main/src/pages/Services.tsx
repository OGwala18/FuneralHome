import { useLanguage } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/card";
import { 
  Flower2, 
  Shield, 
  Plane, 
  ClipboardList, 
  Shovel, 
  Package 
} from "lucide-react";

const services = [
  {
    icon: Flower2,
    title_en: "Funeral Services",
    title_zu: "Izinsizakalo Zomngcwabo",
    items_en: [
      "Complete funeral arrangements",
      "Professional mortuary care",
      "Dignified ceremony planning",
      "Family car and hearse service",
      "Floral arrangements",
      "Memorial programs"
    ],
    items_zu: [
      "Ukuhlelwa okugcwele komngcwabo",
      "Ukunakekelwa kochwepheshe kwama-mortuary",
      "Ukuhlela umcimbi onesihlonipho",
      "Insizakalo yemoto yomndeni ne-hearse",
      "Ukuhleleka kwezimbali",
      "Izinhlelo zesikhumbuzo"
    ]
  },
  {
    icon: Shield,
    title_en: "Funeral Insurance",
    title_zu: "Umshwalense Womngcwabo",
    items_en: [
      "Affordable monthly premiums",
      "Coverage for up to 15 family members",
      "Multiple plan options",
      "Urban and rural coverage",
      "No age limits on certain plans",
      "Transparent terms and conditions"
    ],
    items_zu: [
      "Ama-premium angabizi ngenyanga",
      "Ukumbozwa kwamalungu omndeni ayizi-15",
      "Izinketho eziningi zezinhlelo",
      "Ukumbozwa kwedolobha nasemakhaya",
      "Ayikho imikhawulo yeminyaka ezinhlelweni ezithile",
      "Imigomo nemibandela ecacile"
    ]
  },
  {
    icon: Plane,
    title_en: "Repatriations",
    title_zu: "Ukubuyiswa Kwezidumbu",
    items_en: [
      "National and international repatriations",
      "Full documentation assistance",
      "Coordination with authorities",
      "Safe and dignified transport",
      "Family liaison throughout process",
      "Transparent pricing"
    ],
    items_zu: [
      "Ukubuyiswa kwezidumbu kwezwe lonke nezwe lonke",
      "Usizo olugcwele lwemibhalo",
      "Ukuxhumanisa neziphathimandla",
      "Ukuthuthwa okuphephile nekunesihlonipho",
      "Ukuxhumana nomndeni kuyo yonke inqubo",
      "Amanani acace"
    ]
  },
  {
    icon: ClipboardList,
    title_en: "Pre-Planning",
    title_zu: "Ukuhlela Ngaphambili",
    items_en: [
      "Plan ahead and ease future burden",
      "Lock in today's prices",
      "Personalize your arrangements",
      "Flexible payment options",
      "Peace of mind for family",
      "Professional guidance"
    ],
    items_zu: [
      "Hlela ngaphambili uphungule umthwalo wesikhathi esizayo",
      "Vala amanani anamuhla",
      "Yenza izinhlelelo zakho zibe ezakho",
      "Izinketho zokukhokha eziguquguqukayo",
      "Ukuthula kwengqondo komndeni",
      "Isiqondiso sochwepheshe"
    ]
  },
  {
    icon: Shovel,
    title_en: "Exhumations",
    title_zu: "Ukugedlwa Kwamathuna",
    items_en: [
      "Professional exhumation services",
      "Full legal compliance",
      "Respectful and dignified process",
      "Family support throughout",
      "Coordination with cemeteries",
      "Safe reburial arrangements"
    ],
    items_zu: [
      "Izinsizakalo zochwepheshe zokugeda amathuna",
      "Ukuthobela umthetho ogcwele",
      "Inqubo ehloniphekile nenesihlonipho",
      "Ukusekela umndeni kuyo yonke inqubo",
      "Ukuxhumanisa namathuna",
      "Ukuhlelwa kokungcwaba kabusha okuphephile"
    ]
  },
  {
    icon: Package,
    title_en: "Caskets & Products",
    title_zu: "Amabhokisi Abafileyo Nezikhungo",
    items_en: [
      "Wide range of quality caskets",
      "Various styles and finishes",
      "Affordable pricing options",
      "Photo frames and accessories",
      "Gowns and burial clothing",
      "Traditional and modern options"
    ],
    items_zu: [
      "Inhlobonhlobo yamabhokisi abafileyo asezingeni eliphezulu",
      "Izitayela ezahlukahlukene neziphetho",
      "Izinketho zamanani angabizi",
      "Izinhlaka zezithombe nezinto zokuhlobisa",
      "Ama-gown nezingubo zokungcwaba",
      "Izinketho zendabuko nezesimanje"
    ]
  }
];

export default function Services() {
  const { language, t } = useLanguage();

  return (
    <div className="flex flex-col">
      <section className="bg-secondary/30 py-20">
        <div className="container">
          <div className="max-w-3xl mx-auto text-center">
            <h1 className="mb-6">{t("services_title")}</h1>
            <p className="text-xl leading-relaxed">
              {language === 'en' 
                ? "We provide dignified and affordable funeral services for families in Pietermaritzburg and surrounding areas." 
                : "Sinikeza izinsizakalo zomngcwabo ezinesihlonipho nezingabizi zemindeni ePietermaritzburg nasezindaweni eziseduze."}
            </p>
          </div>
        </div>
      </section>

      <section className="py-20">
        <div className="container">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {services.map((service, index) => {
              const Icon = service.icon;
              return (
                <Card key={index} className="hover:shadow-elevated transition-shadow">
                  <CardContent className="p-8">
                    <div className="flex items-start gap-4 mb-6">
                      <div className="flex-shrink-0 inline-flex items-center justify-center w-14 h-14 bg-primary/10 rounded-full">
                        <Icon className="h-7 w-7 text-primary" />
                      </div>
                      <h3 className="text-2xl">
                        {language === 'en' ? service.title_en : service.title_zu}
                      </h3>
                    </div>
                    
                    <ul className="space-y-3">
                      {(language === 'en' ? service.items_en : service.items_zu).map((item, i) => (
                        <li key={i} className="flex items-start">
                          <span className="inline-block w-2 h-2 bg-primary rounded-full mt-2 mr-3 flex-shrink-0"></span>
                          <span className="text-base">{item}</span>
                        </li>
                      ))}
                    </ul>
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
