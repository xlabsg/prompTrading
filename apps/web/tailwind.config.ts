import type { Config } from "tailwindcss";

export default {
    darkMode: ["class"],
    content: ["./index.html", "./src/**/*.{ts,tsx}"],
    prefix: "",
    theme: {
        container: {
            center: true,
            padding: "1.5rem",
            screens: {
                "2xl": "1320px",
            },
        },
        extend: {
            fontFamily: {
                // One superfamily: sans and mono share metrics, so a number set in
                // mono can sit inline in a sentence without breaking the rhythm.
                sans: [
                    "IBM Plex Sans",
                    "PingFang SC",
                    "Hiragino Sans GB",
                    "Microsoft YaHei",
                    "system-ui",
                    "sans-serif",
                ],
                mono: [
                    "IBM Plex Mono",
                    "ui-monospace",
                    "SFMono-Regular",
                    "Menlo",
                    "monospace",
                ],
            },
            fontSize: {
                // Elements-of-Typographic-Style scale, ~1.25 ratio, tightening as it grows.
                "display-lg": ["clamp(2.75rem, 6vw, 4.5rem)", { lineHeight: "1.02", letterSpacing: "-0.035em" }],
                "display": ["clamp(2rem, 4vw, 3rem)", { lineHeight: "1.08", letterSpacing: "-0.028em" }],
                "title": ["1.5rem", { lineHeight: "1.2", letterSpacing: "-0.018em" }],
            },
            colors: {
                border: "hsl(var(--border))",
                input: "hsl(var(--input))",
                ring: "hsl(var(--ring))",
                background: "hsl(var(--background))",
                foreground: "hsl(var(--foreground))",
                primary: {
                    DEFAULT: "hsl(var(--primary))",
                    foreground: "hsl(var(--primary-foreground))",
                },
                secondary: {
                    DEFAULT: "hsl(var(--secondary))",
                    foreground: "hsl(var(--secondary-foreground))",
                },
                destructive: {
                    DEFAULT: "hsl(var(--destructive))",
                    foreground: "hsl(var(--destructive-foreground))",
                },
                muted: {
                    DEFAULT: "hsl(var(--muted))",
                    foreground: "hsl(var(--muted-foreground))",
                },
                accent: {
                    DEFAULT: "hsl(var(--accent))",
                    foreground: "hsl(var(--accent-foreground))",
                },
                popover: {
                    DEFAULT: "hsl(var(--popover))",
                    foreground: "hsl(var(--popover-foreground))",
                },
                card: {
                    DEFAULT: "hsl(var(--card))",
                    foreground: "hsl(var(--card-foreground))",
                },
                // Market semantics. Reserved for data — never for buttons or chrome.
                long: {
                    DEFAULT: "hsl(var(--long))",
                    soft: "hsl(var(--long-soft))",
                },
                short: {
                    DEFAULT: "hsl(var(--short))",
                    soft: "hsl(var(--short-soft))",
                },
                warn: "hsl(var(--warn))",
                // Syntax highlighting, kept apart from the market semantics so a
                // code comment can never be mistaken for a long position.
                code: {
                    comment: "hsl(var(--code-comment))",
                    keyword: "hsl(var(--code-keyword))",
                    string: "hsl(var(--code-string))",
                    meta: "hsl(var(--code-meta))",
                },
                // Ink chrome. Fixed in both themes so rails read the same everywhere.
                ink: {
                    DEFAULT: "hsl(var(--ink))",
                    raised: "hsl(var(--ink-raised))",
                    line: "hsl(var(--ink-line))",
                    foreground: "hsl(var(--ink-foreground))",
                    muted: "hsl(var(--ink-muted))",
                },
            },
            borderRadius: {
                lg: "var(--radius)",
                md: "calc(var(--radius) - 2px)",
                sm: "calc(var(--radius) - 3px)",
            },
            keyframes: {
                "accordion-down": {
                    from: { height: "0" },
                    to: { height: "var(--radix-accordion-content-height)" },
                },
                "accordion-up": {
                    from: { height: "var(--radix-accordion-content-height)" },
                    to: { height: "0" },
                },
                // The one page-load orchestration, used only on the landing hero.
                "settle": {
                    from: { opacity: "0", transform: "translateY(8px)" },
                    to: { opacity: "1", transform: "translateY(0)" },
                },
                "blink": {
                    "0%, 45%": { opacity: "1" },
                    "50%, 95%": { opacity: "0" },
                },
            },
            animation: {
                "accordion-down": "accordion-down 0.18s ease-out",
                "accordion-up": "accordion-up 0.18s ease-out",
                "settle": "settle 0.5s cubic-bezier(0.2, 0.7, 0.3, 1) both",
                "blink": "blink 1.1s steps(1) infinite",
            },
        },
    },
    plugins: [require("tailwindcss-animate"), require("@tailwindcss/typography")],
} satisfies Config;
