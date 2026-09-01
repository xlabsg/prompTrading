import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface LogoProps {
    size?: "sm" | "md" | "lg";
    variant?: "full" | "icon";
    className?: string;
    animated?: boolean;
}

// 精致几何 Logo - 六边形内嵌 Alpha 符号
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
            {/* Alpha 符号 - 抽象 A 形状 */}
            <path
                d="M20 11L28 27H24L22 23H18L16 27H12L20 11Z"
                className="fill-primary-foreground"
            />
            {/* A 中间横杠 */}
            <path
                d="M17 20H23L22 22H18L17 20Z"
                className="fill-primary"
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
                    Alpha
                </span>
                <span className={cn(
                    "font-display font-bold text-gradient-orange",
                    textSizeClasses[size]
                )}>
                    Forge
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
