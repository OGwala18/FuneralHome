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

const PublicRouter = () => {
  const pathname = usePathname();

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
