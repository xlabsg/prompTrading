import { useState, useEffect } from "react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import { authApi } from "@/lib/api";
import { LogoIcon } from "@/components/Logo";
import { useTranslation } from "react-i18next";

interface AuthDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialStep?: AuthStep;
}

type AuthStep = "login" | "register";

const GoogleLogo = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 48 48"
    aria-hidden="true"
    focusable="false"
  >
    <path
      fill="#EA4335"
      d="M24 9.5c3.5 0 6.6 1.2 9 3.2l6.7-6.7C35.6 2.6 30.1 0 24 0 14.6 0 6.4 5.2 2.3 12.8l7.9 6.1C12.3 13.4 17.7 9.5 24 9.5z"
    />
    <path
      fill="#4285F4"
      d="M46.5 24.5c0-1.6-.1-2.8-.4-4.1H24v8.1h12.7c-.6 3.2-2.4 5.9-5.1 7.7l7.9 6.1c4.6-4.3 7-10.6 7-17.8z"
    />
    <path
      fill="#FBBC05"
      d="M10.2 28.9c-.8-2.3-.8-4.7 0-7l-7.9-6.1C-1.2 21 .1 30.3 7.5 36l7.9-6.1c-2.1-1.6-3.9-3.6-5.2-5.9z"
    />
    <path
      fill="#34A853"
      d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.9-6.1c-2.2 1.5-5.1 2.5-8 2.5-6.3 0-11.7-4-13.7-9.6L2.3 36C6.4 42.8 14.6 48 24 48z"
    />
  </svg>
);

const GitHubLogo = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="currentColor"
    aria-hidden="true"
    focusable="false"
  >
    <path d="M12 .5C5.73.5.5 5.74.5 12.02c0 5.1 3.29 9.43 7.86 10.96.58.11.79-.25.79-.56 0-.28-.01-1.02-.02-2-3.2.7-3.87-1.54-3.87-1.54-.53-1.35-1.3-1.71-1.3-1.71-1.06-.72.08-.71.08-.71 1.17.08 1.79 1.2 1.79 1.2 1.04 1.78 2.73 1.27 3.4.97.11-.75.41-1.27.74-1.56-2.55-.29-5.23-1.28-5.23-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11.07 11.07 0 0 1 2.9-.39c.99 0 1.98.13 2.9.39 2.2-1.49 3.18-1.18 3.18-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.42-2.69 5.4-5.25 5.68.42.36.8 1.08.8 2.18 0 1.58-.01 2.86-.01 3.25 0 .31.21.68.8.56 4.57-1.53 7.86-5.86 7.86-10.96C23.5 5.73 18.27.5 12 .5z" />
  </svg>
);

export function AuthDialog({ open, onOpenChange, initialStep = "register" }: AuthDialogProps) {
  const [step, setStep] = useState<AuthStep>(initialStep);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const { t } = useTranslation();

  // Sync step with initialStep when it changes
  useEffect(() => {
    setStep(initialStep);
  }, [initialStep]);

  const handleOAuth = async (provider: "github" | "google") => {
    setIsLoading(true);
    setError("");

    try {
      const response = await authApi.startOAuth(provider, window.location.pathname);
      window.location.assign(response.auth_url);
    } catch (err: any) {
      const errorMsg = err?.message || "";
      setError(`${t("auth.authorizationFailed")}: ${errorMsg}`);
      setIsLoading(false);
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      setStep(initialStep);
      setError("");
    }
    onOpenChange(newOpen);
  };

  const renderOAuthButtons = () => (
    <div className="w-full mt-5 space-y-2.5">
      <Button
        variant="outline"
        className="w-full h-11 text-sm font-medium justify-start px-4 gap-3 bg-stone-100 hover:bg-stone-200 border-stone-200"
        onClick={() => handleOAuth("google")}
        disabled={isLoading}
      >
        {isLoading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <GoogleLogo className="w-5 h-5" />
        )}
        {t("common.continue")} Google
      </Button>
      <Button
        variant="outline"
        className="w-full h-11 text-sm font-medium justify-start px-4 gap-3 bg-stone-100 hover:bg-stone-200 border-stone-200"
        onClick={() => handleOAuth("github")}
        disabled={isLoading}
      >
        {isLoading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <GitHubLogo className="w-5 h-5" />
        )}
        {t("common.continue")} GitHub
      </Button>
    </div>
  );

  const renderLoginStep = () => (
    <>
      <div className="mt-4 space-y-0.5">
        <h1 className="text-xl font-semibold tracking-tight">
          {t("auth.welcomeBack")}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t("auth.signInSubtitle")}
        </p>
      </div>

      {error && (
        <div className="w-full mt-4 p-3 rounded-lg bg-red-50 border border-red-200">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      {renderOAuthButtons()}

      <div className="w-full mt-4 text-center">
        <p className="text-sm text-muted-foreground">
          {t("auth.dontHaveAccount")}{" "}
          <button
            onClick={() => {
              setStep("register");
              setError("");
            }}
            className="text-primary hover:underline font-medium"
          >
            {t("auth.signUpNow")}
          </button>
        </p>
      </div>
    </>
  );

  const renderRegisterStep = () => (
    <>
      <div className="mt-4 space-y-0.5">
        <h1 className="text-xl font-semibold tracking-tight">
          {t("auth.createAccount")}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t("auth.createAccountSubtitle")}
        </p>
      </div>

      {error && (
        <div className="w-full mt-4 p-3 rounded-lg bg-red-50 border border-red-200">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      {renderOAuthButtons()}

      <div className="w-full mt-4 text-center">
        <p className="text-sm text-muted-foreground">
          {t("auth.alreadyHaveAccount")}{" "}
          <button
            onClick={() => {
              setStep("login");
              setError("");
            }}
            className="text-primary hover:underline font-medium"
          >
            {t("auth.signInNow")}
          </button>
        </p>
      </div>
    </>
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md p-0 gap-0">
        <div className="flex flex-col items-start p-6">
          <LogoIcon size="lg" />

          {step === "login" && renderLoginStep()}
          {step === "register" && renderRegisterStep()}

          <p className="w-full text-center text-xs text-muted-foreground mt-4">
            {t("auth.termsPrefix")}{" "}
            <a href="#" className="underline hover:text-foreground">
              {t("auth.terms")}
            </a>{" "}
            {t("common.and")}{" "}
            <a href="#" className="underline hover:text-foreground">
              {t("auth.privacy")}
            </a>
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
