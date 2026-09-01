import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Header from "@/components/landing/Header";
import Hero from "@/components/landing/Hero";
import Features from "@/components/landing/Features";
import HowItWorks from "@/components/landing/HowItWorks";
import CTA from "@/components/landing/CTA";
import Footer from "@/components/landing/Footer";
import { AuthDialog } from "@/components/auth/AuthDialog";
import { authApi } from "@/lib/api";

type AuthStep = "login" | "register";

const Index = () => {
    const navigate = useNavigate();
    const [isAuthOpen, setIsAuthOpen] = useState(false);
    const [authStep, setAuthStep] = useState<AuthStep>("register");

    // Check auth status
    const { data: authData } = useQuery({
        queryKey: ["auth-me"],
        queryFn: async () => {
            try {
                return await authApi.me();
            } catch {
                return null;
            }
        },
        retry: false,
    });

    const isAuthed = Boolean(authData?.user);

    // Redirect to console if logged in
    useEffect(() => {
        if (isAuthed) {
            navigate("/console");
        }
    }, [isAuthed, navigate]);

    const handleOpenAuth = (step?: AuthStep) => {
        setAuthStep(step || "register");
        setIsAuthOpen(true);
    };

    return (
        <div className="min-h-screen bg-background">
            <Header onOpenAuth={handleOpenAuth} />
            <Hero onOpenAuth={handleOpenAuth} />
            <Features />
            <HowItWorks />
            <CTA />
            <Footer />

            <AuthDialog
                open={isAuthOpen}
                onOpenChange={setIsAuthOpen}
                initialStep={authStep}
            />
        </div>
    );
};

export default Index;
