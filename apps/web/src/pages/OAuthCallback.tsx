import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { apiBaseUrl } from "@/lib/api";

const OAuthCallback = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const { t } = useTranslation();

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const provider = window.location.pathname.split("/")[3]; // github or google

    if (!code || !state) {
      setError(t("errors.authMessage"));
      return;
    }

    // The OAuth callback is handled by the API server
    // The API server will set a session cookie and redirect to the app
    // This page just shows a loading state while that happens

    // Construct the API callback URL
    const apiCallbackUrl = `${apiBaseUrl()}/api/auth/oauth/${provider}/callback?code=${code}&state=${state}`;

    // Redirect to API callback endpoint
    window.location.href = apiCallbackUrl;
  }, [searchParams, navigate]);

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-red-600 mb-4">{t("errors.authTitle")}</h1>
          <p className="text-muted-foreground">{error}</p>
          <button
            onClick={() => navigate("/")}
            className="mt-4 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
          >
            {t("errors.goHome")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
        <p className="text-muted-foreground">{t("auth.completing", { defaultValue: "Completing authentication..." })}</p>
      </div>
    </div>
  );
};

export default OAuthCallback;
