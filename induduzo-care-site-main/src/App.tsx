import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";

import PublicLayout from "@/components/layout/PublicLayout";
import AuthLayout from "@/components/layout/AuthLayout";
import PortalLayout from "@/components/layout/PortalLayout";

import Home from "./pages/Home";
import About from "./pages/About";
import Services from "./pages/Services";
import Contact from "./pages/Contact";
import Join from "./pages/Join";
import Gallery from "./pages/Gallery";
import Testimonials from "./pages/Testimonials";
import Founder from "./pages/Founder";
import NotFound from "./pages/NotFound";

import AuthPage from "@/features/auth/AuthPage";
import DashboardPage from "@/features/customer/DashboardPage";
import PolicyPage from "@/features/customer/PolicyPage";
import FamilyPage from "@/features/customer/FamilyPage";
import PaymentsPage from "@/features/customer/PaymentsPage";
import ClaimsPage from "@/features/customer/ClaimsPage";
import ClaimCasePage from "@/features/customer/ClaimCasePage";
import FuneralServicesPage from "@/features/customer/FuneralServicesPage";
import ProfilePage from "@/features/customer/ProfilePage";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          {/* Public website */}
          <Route element={<PublicLayout />}>
            <Route path="/" element={<Home />} />
            <Route path="/about" element={<About />} />
            <Route path="/services" element={<Services />} />
            <Route path="/contact" element={<Contact />} />
            <Route path="/join" element={<Join />} />
            <Route path="/gallery" element={<Gallery />} />
            <Route path="/testimonials" element={<Testimonials />} />
            <Route path="/founder" element={<Founder />} />
          </Route>

          {/* Auth */}
          <Route element={<AuthLayout />}>
            <Route path="/auth" element={<AuthPage />} />
          </Route>

          {/* Customer portal */}
          <Route path="/portal/customer" element={<PortalLayout />}>
            <Route index element={<DashboardPage />} />
            <Route path="policy" element={<PolicyPage />} />
            <Route path="family" element={<FamilyPage />} />
            <Route path="payments" element={<PaymentsPage />} />
            <Route path="claims" element={<ClaimsPage />} />
            <Route path="claims/:caseId" element={<ClaimCasePage />} />
            <Route path="funeral-services" element={<FuneralServicesPage />} />
            <Route path="profile" element={<ProfilePage />} />
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
