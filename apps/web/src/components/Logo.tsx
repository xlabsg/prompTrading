import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface LogoProps {
    size?: "sm" | "md" | "lg";
    variant?: "full" | "icon";
    className?: string;
    animated?: boolean;
}

// 精致几何 Logo - 六边形内嵌 Prompt 提示符与交易上升条形
const LogoIcon = ({
    size = "md",
    animated = false,
    className
}: {
    size?: "sm" | "md" | "lg";
    animated?: boolean;
    className?: string;
}) => {
    const sizeClasses = {
        sm: "w-6 h-6",
        md: "w-8 h-8",
        lg: "w-10 h-10",
    };

    const svgContent = (
        <svg
            viewBox="0 0 40 40"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="w-full h-full"
        >
            {/* 外层六边形 - 代表稳固的基础 */}
            <path
                d="M20 2L36 11V29L20 38L4 29V11L20 2Z"
                className="fill-primary"
            />
            {/* 内层六边形 - 渐变层次 */}
            <path
                d="M20 7L31 13.5V26.5L20 33L9 26.5V13.5L20 7Z"
                className="fill-primary-foreground/20"
            />
            {/* Prompt 提示符 > */}
            <path
                d="M12 14.5L18 20L12 25.5H15.2L21.2 20L15.2 14.5H12Z"
                className="fill-primary-foreground"
            />
            {/* 交易上升柱线 (Trading Bars) */}
            <rect
                x="23"
                y="19"
                width="2.2"
                height="6.5"
                rx="0.5"
                className="fill-primary-foreground"
            />
            <rect
                x="26.5"
                y="14.5"
                width="2.2"
                height="11"
                rx="0.5"
                className="fill-primary-foreground"
            />
        </svg>
    );

    if (animated) {
        return (
            <motion.div
                className={cn("relative", sizeClasses[size], className)}
                initial={{ rotate: -10, scale: 0.9 }}
                animate={{ rotate: 0, scale: 1 }}
                transition={{ duration: 0.5, type: "spring" }}
            >
                {svgContent}
            </motion.div>
        );
    }

    return (
        <div className={cn("relative", sizeClasses[size], className)}>
            {svgContent}
        </div>
    );
};

const Logo = ({
    size = "md",
    variant = "full",
    className,
    animated = false
}: LogoProps) => {
    const textSizeClasses = {
        sm: "text-lg",
        md: "text-xl lg:text-2xl",
        lg: "text-2xl lg:text-3xl",
    };

    if (variant === "icon") {
        return <LogoIcon size={size} animated={animated} className={className} />;
    }

    const content = (
        <>
            <LogoIcon size={size} animated={animated} />
            <div className="flex items-center gap-0.5">
                <span className={cn(
                    "font-display font-bold text-foreground",
                    textSizeClasses[size]
                )}>
                    Promp
                </span>
                <span className={cn(
                    "font-display font-bold text-gradient-orange",
                    textSizeClasses[size]
                )}>
                    Trading
                </span>
            </div>
        </>
    );

    if (animated) {
        return (
            <motion.a
                href="/"
                className={cn("flex items-center gap-2", className)}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.5 }}
            >
                {content}
            </motion.a>
        );
    }

    return (
        <a href="/" className={cn("flex items-center gap-2", className)}>
            {content}
        </a>
    );
};

export { Logo, LogoIcon };
export default Logo;
