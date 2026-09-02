import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AlertCircle, Mail, Home } from "lucide-react";
import { useTranslation } from "react-i18next";

const AuthError = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [errorData, setErrorData] = useState<{
    title: string;
    message: string;
    showWaitlist: boolean;
  }>({
    title: t("errors.authTitle"),
    message: t("errors.authMessage"),
    showWaitlist: false,
  });

  useEffect(() => {
    const error = searchParams.get("error");

    switch (error) {
      case "registration_required":
        setErrorData({
          title: t("errors.accountNotFoundTitle"),
          message: t("errors.accountNotFoundMessage"),
          showWaitlist: true,
        });
        break;
      case "invalid_state":
      case "state_expired":
        setErrorData({
          title: t("errors.sessionExpiredTitle"),
          message: t("errors.sessionExpiredMessage"),
          showWaitlist: false,
        });
        break;
      case "unsupported_provider":
        setErrorData({
          title: t("errors.unsupportedProviderTitle"),
          message: t("errors.unsupportedProviderMessage"),
          showWaitlist: false,
        });
        break;
      case "invite_missing":
      case "invite_expired":
      case "invite_exhausted":
        setErrorData({
          title: t("errors.invalidInviteTitle"),
          message: t("errors.invalidInviteMessage"),
          showWaitlist: true,
        });
        break;
      default:
        setErrorData({
          title: t("errors.authTitle"),
          message: t("errors.authMessage"),
          showWaitlist: false,
        });
    }
  }, [searchParams, t]);

  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <div className="max-w-md w-full mx-4">
        <div className="bg-card border border-border rounded-xl p-8 text-center">
          {/* Error Icon */}
          <div className="flex justify-center mb-4">
            <div className="p-3 bg-destructive/10 rounded-full">
              <AlertCircle className="h-8 w-8 text-destructive" />
            </div>
          </div>

          {/* Error Message */}
          <h1 className="text-2xl font-bold mb-2">{errorData.title}</h1>
          <p className="text-muted-foreground mb-6">{errorData.message}</p>

          {/* Waitlist CTA */}
          {errorData.showWaitlist && (
            <div className="bg-muted rounded-lg p-4 mb-6">
              <p className="text-sm text-muted-foreground mb-3">
                {t("auth.waitlistTitle")}
              </p>
              <a
                href="mailto:info@example.com?subject=Waitlist Request - PromptTrading"
                className="inline-flex items-center justify-center gap-2 w-full px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
              >
                <Mail size={16} />
                <span>{t("auth.waitlistCta")}</span>
              </a>
            </div>
          )}

          {/* Action Buttons */}
          <button
            onClick={() => navigate("/")}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-border rounded-lg hover:bg-muted transition-colors"
          >
            <Home size={16} />
            <span>{t("errors.goHome")}</span>
          </button>
        </div>

        {/* Help Text */}
        <p className="text-center text-sm text-muted-foreground mt-4">
          {t("errors.needHelp")}{" "}
          <a href="mailto:info@example.com" className="text-primary hover:underline">
            info@example.com
          </a>
        </p>
      </div>
    </div>
  );
};

export default AuthError;
