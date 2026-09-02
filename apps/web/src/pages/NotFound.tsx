import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useTranslation } from "react-i18next";

const NotFound = () => {
    const { t } = useTranslation();
    return (
        <div className="flex min-h-screen items-center justify-center bg-background px-6">
            <div className="w-full max-w-md">
                <p className="numeric text-sm text-muted-foreground">404</p>
                <h1 className="mt-3 text-title font-semibold text-foreground">{t("errors.notFoundTitle")}</h1>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {t("errors.notFoundMessage")}
                </p>
                <Button className="mt-7" asChild>
                    <Link to="/">{t("errors.backToHome")}</Link>
                </Button>
            </div>
        </div>
    );
};

export default NotFound;
