import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Home } from "lucide-react";
import { useTranslation } from "react-i18next";

const NotFound = () => {
    const { t } = useTranslation();
    return (
        <div className="min-h-screen bg-background flex items-center justify-center">
            <div className="text-center">
                <h1 className="text-9xl font-display font-bold text-primary/20 mb-4">404</h1>
                <h2 className="text-2xl font-semibold text-foreground mb-2">{t("errors.notFoundTitle")}</h2>
                <p className="text-muted-foreground mb-8">
                    {t("errors.notFoundMessage")}
                </p>
                <Link to="/">
                    <Button className="gap-2">
                        <Home className="w-4 h-4" />
                        {t("errors.backToHome")}
                    </Button>
                </Link>
            </div>
        </div>
    );
};

export default NotFound;
