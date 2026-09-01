import { Strategy } from "@/pages/Console";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FileText, TrendingUp, Shield, AlertTriangle, CheckCircle } from "lucide-react";
import { useTranslation } from "react-i18next";

interface ReportViewProps {
    strategy: Strategy | null;
}

const ReportView = ({ strategy }: ReportViewProps) => {
    const { t } = useTranslation();
    return (
        <div className="h-full overflow-auto p-6">
            <div className="max-w-4xl mx-auto space-y-6">
                <div className="flex items-center gap-4 mb-8">
                    <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center">
                        <FileText className="w-6 h-6 text-primary" />
                    </div>
                    <div>
                        <h2 className="text-2xl font-bold text-foreground">{t("reportView.title")}</h2>
                        <p className="text-muted-foreground">{strategy?.name || t("reportView.defaultStrategyName")}</p>
                    </div>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <TrendingUp className="w-5 h-5 text-primary" />
                            {t("reportView.summaryTitle")}
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="text-muted-foreground">
                        <p>{t("reportView.summaryText")}</p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Shield className="w-5 h-5 text-primary" />
                            {t("reportView.riskTitle")}
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="flex items-start gap-3 p-3 bg-green-500/10 rounded-lg">
                            <CheckCircle className="w-5 h-5 text-green-500" />
                            <p className="text-sm">{t("reportView.riskGood")}</p>
                        </div>
                        <div className="flex items-start gap-3 p-3 bg-yellow-500/10 rounded-lg">
                            <AlertTriangle className="w-5 h-5 text-yellow-500" />
                            <p className="text-sm">{t("reportView.riskWarn")}</p>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
};

export default ReportView;
