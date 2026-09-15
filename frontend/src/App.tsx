import { useEffect } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { usePathname } from "@/lib/navigation";

import PublicLayout from "@/components/layout/PublicLayout";

import Home from "./pages/Home";
import About from "./pages/About";
import Services from "./pages/Services";
import Contact from "./pages/Contact";
import Join from "./pages/Join";
import Register from "./pages/Register";
import RegisterDetails from "./pages/RegisterDetails";
import Gallery from "./pages/Gallery";
import Testimonials from "./pages/Testimonials";
import Founder from "./pages/Founder";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const pageMetadata: Record<string, { title: string; description: string }> = {
  "/": {
    title: "Induduzo Funeral Home - Funeral Services in Pietermaritzburg",
    description: "Induduzo Funeral Home provides compassionate funeral services and plans in Pietermaritzburg and the KwaZulu-Natal Midlands.",
  },
  "/about": {
    title: "About Induduzo Funeral Home | Pietermaritzburg",
    description: "Learn about Induduzo Funeral Home, a family-run funeral home serving Pietermaritzburg and the KwaZulu-Natal Midlands since the 1980s.",
  },
  "/services": {
    title: "Funeral Services | Induduzo Funeral Home",
    description: "Explore funeral arrangements, repatriations, pre-planning, exhumations, caskets and related services from Induduzo Funeral Home.",
  },
  "/contact": {
    title: "Contact Induduzo Funeral Home | Edendale, Pietermaritzburg",
    description: "Call, WhatsApp or visit Induduzo Funeral Home on Edendale Main Road, Kwadaya, Pietermaritzburg. Find directions and Google reviews.",
  },
  "/join": {
    title: "Funeral Plans | Induduzo Funeral Home",
    description: "Compare current funeral plan options from Induduzo Funeral Home in Pietermaritzburg.",
  },
  "/gallery": {
    title: "Gallery | Induduzo Funeral Home",
    description: "View the Induduzo Funeral Home gallery.",
  },
  "/testimonials": {
    title: "Testimonials | Induduzo Funeral Home",
    description: "Read testimonials from families served by Induduzo Funeral Home.",
  },
  "/founder": {
    title: "Our Founder | Induduzo Funeral Home",
    description: "Read the founder story of Induduzo Funeral Home.",
  },
  "/register": {
    title: "Register Interest | Induduzo Funeral Home",
    description: "Register your interest in an Induduzo Funeral Home funeral plan.",
  },
  "/register/details": {
    title: "Registration Details | Induduzo Funeral Home",
    description: "Complete your Induduzo Funeral Home plan registration details.",
  },
};

const PublicRouter = () => {
  const pathname = usePathname();

  useEffect(() => {
    const metadata = pageMetadata[pathname];
    if (!metadata) return;

    const url = `https://induduzo.co.za${pathname === "/" ? "/" : pathname}`;
    document.title = metadata.title;
    document.querySelector('meta[name="description"]')?.setAttribute("content", metadata.description);
    document.querySelector('link[rel="canonical"]')?.setAttribute("href", url);
    document.querySelector('meta[property="og:url"]')?.setAttribute("content", url);
  }, [pathname]);

  const page = (() => {
    switch (pathname) {
      case "/":
        return <Home />;
      case "/about":
        return <About />;
      case "/services":
        return <Services />;
      case "/contact":
        return <Contact />;
      case "/join":
        return <Join />;
      case "/register":
        return <Register />;
      case "/register/details":
        return <RegisterDetails />;
      case "/gallery":
        return <Gallery />;
      case "/testimonials":
        return <Testimonials />;
      case "/founder":
        return <Founder />;
      default:
        return null;
    }
  })();

  return page ? <PublicLayout>{page}</PublicLayout> : <NotFound />;
};

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <PublicRouter />
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
