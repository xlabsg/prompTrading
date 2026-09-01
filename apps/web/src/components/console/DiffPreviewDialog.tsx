import { FC } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { DiffViewer } from "./DiffViewer";
import { OperationsList } from "./OperationsList";
import type { RefineProposal } from "@/lib/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FileCode, List } from "lucide-react";
import { useTranslation } from "react-i18next";

interface DiffPreviewDialogProps {
    proposal: RefineProposal;
    onClose: () => void;
}

export const DiffPreviewDialog: FC<DiffPreviewDialogProps> = ({ proposal, onClose }) => {
    const { t } = useTranslation();
    const hasDiff = Boolean(proposal.patch);
    const hasOperations = Boolean(proposal.change_spec?.operations && proposal.change_spec.operations.length > 0);

    return (
        <Dialog open onOpenChange={onClose}>
            <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle>{t("diffPreview.title")}</DialogTitle>
                    <DialogDescription>
                        {t("diffPreview.subtitle")}
                    </DialogDescription>
                </DialogHeader>

                <div className="flex-1 min-h-0">
                    {hasOperations && hasDiff ? (
                        // Show both operations and diff in tabs
                        <Tabs defaultValue="operations" className="h-full flex flex-col">
                            <TabsList className="grid w-full grid-cols-2">
                                <TabsTrigger value="operations" className="flex items-center gap-2">
                                    <List size={14} />
                                    {t("diffPreview.tabs.operations", { count: proposal.change_spec!.operations.length })}
                                </TabsTrigger>
                                <TabsTrigger value="diff" className="flex items-center gap-2">
                                    <FileCode size={14} />
                                    {t("diffPreview.tabs.diff")}
                                </TabsTrigger>
                            </TabsList>

                            <TabsContent value="operations" className="flex-1 overflow-auto mt-4">
                                <OperationsList operations={proposal.change_spec!.operations} />
                            </TabsContent>

                            <TabsContent value="diff" className="flex-1 overflow-auto mt-4">
                                {hasDiff ? (
                                    <DiffViewer diffText={proposal.patch!} />
                                ) : (
                                    <div className="text-sm text-muted-foreground p-4 text-center">
                                        {t("diffPreview.diffPending")}
                                    </div>
                                )}
                            </TabsContent>
                        </Tabs>
                    ) : hasOperations ? (
                        // Show only operations
                        <div className="overflow-auto h-full">
                            <div className="mb-4">
                                <h3 className="text-sm font-medium flex items-center gap-2">
                                    <List size={14} />
                                    {t("diffPreview.planned", { count: proposal.change_spec!.operations.length })}
                                </h3>
                            </div>
                            <OperationsList operations={proposal.change_spec!.operations} />
                            <div className="mt-4 p-3 bg-muted/50 rounded-md text-xs text-muted-foreground">
                                <p>
                                    {t("diffPreview.note")}
                                </p>
                            </div>
                        </div>
                    ) : hasDiff ? (
                        // Show only diff (legacy mode)
                        <div className="h-full">
                            <DiffViewer diffText={proposal.patch!} />
                        </div>
                    ) : (
                        // No preview available
                        <div className="flex items-center justify-center h-full">
                            <div className="text-center space-y-2">
                                <p className="text-sm text-muted-foreground">
                                    {t("diffPreview.emptyTitle")}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                    {t("diffPreview.emptySubtitle")}
                                </p>
                            </div>
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
};
