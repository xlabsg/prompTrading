import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { useEffect } from "react";
import Index from "./pages/Index";
import Console from "./pages/Console";
import Trending from "./pages/Trending";
import TemplatesPage from "./pages/Templates";
import SubscriptionsPage from "./pages/Subscriptions";
import TemplateConsole from "./pages/TemplateConsole";
import NotFound from "./pages/NotFound";
import OAuthCallback from "./pages/OAuthCallback";
import AuthError from "./pages/AuthError";
import AdminTrending from "./pages/AdminTrending";
import { initGa4, trackPageView } from "@/lib/analytics/ga4";

const queryClient = new QueryClient();

function AnalyticsRouteTracker() {
    const location = useLocation();

    useEffect(() => {
        initGa4();
        trackPageView(`${location.pathname}${location.search || ""}`);
    }, [location.pathname, location.search]);

    return null;
}

const App = () => (
    <QueryClientProvider client={queryClient}>
        <TooltipProvider>
            <Toaster />
            <Sonner />
            <BrowserRouter>
                <AnalyticsRouteTracker />
                <Routes>
                    <Route path="/" element={<Console />} />
                    <Route path="/strategy/:strategyId" element={<Console />} />
                    <Route path="/strategy/:strategyId/:tab" element={<Console />} />
                    <Route path="/trending" element={<Trending />} />
                    <Route path="/templates" element={<TemplatesPage />} />
                    <Route path="/template/:templateId" element={<TemplateConsole />} />
                    <Route path="/template/:templateId/:tab" element={<TemplateConsole />} />
                    <Route path="/subscriptions" element={<SubscriptionsPage />} />
                    <Route path="/admin/trending" element={<AdminTrending />} />
                    <Route path="/landing-page" element={<Index />} />
                    <Route path="/auth/oauth/:provider/callback" element={<OAuthCallback />} />
                    <Route path="/auth/error" element={<AuthError />} />
                    <Route path="*" element={<NotFound />} />
                </Routes>
            </BrowserRouter>
        </TooltipProvider>
    </QueryClientProvider>
);

export default App;
