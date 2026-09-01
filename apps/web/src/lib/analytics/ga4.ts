declare global {
    interface Window {
        dataLayer?: unknown[];
        gtag?: (...args: unknown[]) => void;
    }
}

let isInitialized = false;

function _getEnvMeasurementId(): string {
    return (import.meta.env.VITE_GA_MEASUREMENT_ID || "").trim();
}

function _getEnvCookieDomain(): string {
    return (import.meta.env.VITE_GA_COOKIE_DOMAIN || "").trim();
}

export function isGaEnabled(): boolean {
    return Boolean(_getEnvMeasurementId());
}

export function initGa4(): void {
    if (isInitialized) return;

    const measurementId = _getEnvMeasurementId();
    if (!measurementId) return;
    if (typeof window === "undefined" || typeof document === "undefined") return;

    const scriptSrc = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
    const hasScript = Boolean(document.querySelector(`script[src="${scriptSrc}"]`));
    if (!hasScript) {
        const script = document.createElement("script");
        script.async = true;
        script.src = scriptSrc;
        document.head.appendChild(script);
    }

    window.dataLayer = window.dataLayer || [];
    window.gtag =
        window.gtag ||
        function gtag() {
            // Match the official gtag.js shim behavior: dataLayer.push(arguments)
            // eslint-disable-next-line prefer-rest-params
            window.dataLayer?.push(arguments as unknown as never);
        };

    window.gtag("js", new Date());

    const cookieDomain = _getEnvCookieDomain();
    window.gtag(
        "config",
        measurementId,
        cookieDomain ? { send_page_view: false, cookie_domain: cookieDomain } : { send_page_view: false }
    );

    isInitialized = true;
}

export function trackPageView(pagePath: string): void {
    const measurementId = _getEnvMeasurementId();
    if (!measurementId) return;
    if (typeof window === "undefined") return;
    if (typeof window.gtag !== "function") return;

    window.gtag("event", "page_view", {
        send_to: measurementId,
        page_path: pagePath,
        page_location: window.location.href,
        page_title: typeof document !== "undefined" ? document.title : undefined,
    });
}

export function trackEvent(eventName: string, params?: Record<string, unknown>): void {
    const measurementId = _getEnvMeasurementId();
    if (!measurementId) return;
    if (typeof window === "undefined") return;
    if (typeof window.gtag !== "function") return;

    window.gtag("event", eventName, { send_to: measurementId, ...(params || {}) });
}
