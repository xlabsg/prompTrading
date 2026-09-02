import { cn } from "@/lib/utils";

interface LogoProps {
    size?: "sm" | "md" | "lg";
    variant?: "full" | "icon";
    className?: string;
    /** Set when the logo sits on an ink surface (nav rail, landing header). */
    onInk?: boolean;
    /** Kept for call sites that still pass it; the mark no longer animates. */
    animated?: boolean;
}

const sizeClasses = {
    sm: "w-[22px] h-[22px]",
    md: "w-7 h-7",
    lg: "w-9 h-9",
};

/**
 * A candle and its wick inside a frame: the smallest true drawing of what the
 * product operates on, rather than a generic geometric mark.
 */
const LogoIcon = ({
    size = "md",
    className,
}: {
    size?: "sm" | "md" | "lg";
    className?: string;
}) => (
    <div className={cn("relative shrink-0", sizeClasses[size], className)}>
        <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" className="h-full w-full">
            <rect x="1" y="1" width="30" height="30" rx="5" className="fill-primary" />
            <path d="M11 7v18" stroke="white" strokeWidth="1.6" strokeOpacity="0.55" strokeLinecap="round" />
            <rect x="8" y="11" width="6" height="11" rx="1" fill="white" />
            <path d="M21 9v16" stroke="white" strokeWidth="1.6" strokeOpacity="0.55" strokeLinecap="round" />
            <rect x="18" y="13" width="6" height="7" rx="1" fill="white" fillOpacity="0.45" />
        </svg>
    </div>
);

const textSizeClasses = {
    sm: "text-[15px]",
    md: "text-lg",
    lg: "text-xl",
};

const Logo = ({ size = "md", variant = "full", className, onInk = false }: LogoProps) => {
    if (variant === "icon") {
        return <LogoIcon size={size} className={className} />;
    }

    return (
        <a href="/" className={cn("flex items-center gap-2.5", className)}>
            <LogoIcon size={size} />
            <span
                className={cn(
                    "font-semibold tracking-[-0.02em]",
                    textSizeClasses[size],
                    onInk ? "text-ink-foreground" : "text-foreground",
                )}
            >
                AlphaForge
            </span>
        </a>
    );
};

export { Logo, LogoIcon };
export default Logo;
