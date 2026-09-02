import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Copy, Check, Search, Folder, File, ChevronRight, ChevronDown, Loader2, Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import type { Strategy, StrategyGitCompareFile } from "@/lib/types";
import { reposApi, strategiesApi } from "@/lib/api";
import { DiffViewer } from "@/components/console/DiffViewer";
import { useTranslation } from "react-i18next";

interface CodeViewProps {
    strategy: Strategy | null;
}

type RightPanelMode = "code" | "changes";

const SYSTEM_STRATEGY_FILE_PATHS = new Set([
    "strategy/overview.md",
    "strategy/strategy_spec.yaml",
    "strategy/params_schema.json",
    "strategy/strategy_meta.json",
    "strategy/strategy_protocol.json",
]);

interface FileNode {
    name: string;
    type: "file" | "folder";
    children?: FileNode[];
    path: string;
    content?: string;
}

const buildFileTreeFromPaths = (
    paths: string[],
    contentByPath?: Record<string, string>
): FileNode[] => {
    const root: FileNode[] = [];

    const ensureFolder = (nodes: FileNode[], name: string, path: string) => {
        const existing = nodes.find((node) => node.type === "folder" && node.name === name);
        if (existing) return existing;
        const folder: FileNode = { name, type: "folder", path, children: [] };
        nodes.push(folder);
        return folder;
    };

    for (const filePath of paths) {
        const parts = filePath.split("/").filter(Boolean);
        let currentNodes = root;
        let currentPath = "";
        parts.forEach((part, index) => {
            currentPath = currentPath ? `${currentPath}/${part}` : part;
            const isFile = index === parts.length - 1;
            if (isFile) {
                currentNodes.push({
                    name: part,
                    type: "file",
                    path: currentPath,
                    content: contentByPath?.[filePath],
                });
            } else {
                const folder = ensureFolder(currentNodes, part, currentPath);
                currentNodes = folder.children ?? [];
                folder.children = currentNodes;
            }
        });
    }

    const sortTree = (nodes: FileNode[]) => {
        nodes.sort((a, b) => {
            if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
            return a.name.localeCompare(b.name);
        });
        for (const node of nodes) {
            if (node.children) sortTree(node.children);
        }
    };

    sortTree(root);
    return root;
};

const shortCommit = (hash: string | null) => (hash ? hash.slice(0, 7) : "none");

// Flatten file tree to get all files
const getAllFiles = (nodes: FileNode[]): FileNode[] => {
    const files: FileNode[] = [];
    const traverse = (nodeList: FileNode[]) => {
        for (const node of nodeList) {
            if (node.type === "file") {
                files.push(node);
            }
            if (node.children) {
                traverse(node.children);
            }
        }
    };
    traverse(nodes);
    return files;
};

const FileTreeItem = ({
    node,
    depth = 0,
    selectedFile,
    onSelect
}: {
    node: FileNode;
    depth?: number;
    selectedFile: string | null;
    onSelect: (node: FileNode) => void;
}) => {
    const [expanded, setExpanded] = useState(depth === 0);

    if (node.type === "folder") {
        return (
            <div>
                <button
                    onClick={() => setExpanded(!expanded)}
                    className="w-full flex items-center gap-1 px-2 py-1 text-sm hover:bg-muted rounded-md text-muted-foreground hover:text-foreground"
                    style={{ paddingLeft: `${depth * 12 + 8}px` }}
                >
                    {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    <Folder size={14} className="text-primary" />
                    <span>{node.name}</span>
                </button>
                {expanded && node.children?.map((child, idx) => (
                    <FileTreeItem
                        key={idx}
                        node={child}
                        depth={depth + 1}
                        selectedFile={selectedFile}
                        onSelect={onSelect}
                    />
                ))}
            </div>
        );
    }

    return (
        <button
            onClick={() => onSelect(node)}
            className={cn(
                "w-full flex items-center gap-2 px-2 py-1 text-sm rounded-md",
                selectedFile === node.path
                    ? "bg-primary/10 text-primary"
                    : "hover:bg-muted text-muted-foreground hover:text-foreground"
            )}
            style={{ paddingLeft: `${depth * 12 + 24}px` }}
        >
            <File size={14} />
            <span>{node.name}</span>
        </button>
    );
};

const CodeView = ({ strategy }: CodeViewProps) => {
    const { t } = useTranslation();
    const [copied, setCopied] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [activeTab, setActiveTab] = useState<"files" | "search">("files");
    const [fileDialogOpen, setFileDialogOpen] = useState(false);
    const [showSystemFiles, setShowSystemFiles] = useState(false);
    const [rightPanelMode, setRightPanelMode] = useState<RightPanelMode>("code");
    const [selectedChangedPath, setSelectedChangedPath] = useState<string | null>(null);
    const [isChangesListExpanded, setIsChangesListExpanded] = useState(true);
    const isRepoStrategy = Boolean(strategy?.repo_id);
    const compareMode = isRepoStrategy ? "repo" : "workspace";

    const strategyFilesQuery = useQuery({
        queryKey: ["strategy-files", strategy?.id],
        queryFn: () => strategy ? strategiesApi.getFiles(strategy.id) : Promise.resolve({ files: [] }),
        enabled: Boolean(strategy && !isRepoStrategy && strategy.chat_status === "done"),
    });

    const repoQuery = useQuery({
        queryKey: ["repo", strategy?.repo_id],
        queryFn: () => reposApi.get(strategy?.repo_id || ""),
        enabled: Boolean(strategy?.repo_id),
    });

    const repoBranch = useMemo(() => {
        if (!repoQuery.data) return undefined;
        return repoQuery.data.tracked_branches?.[0] || repoQuery.data.default_branch;
    }, [repoQuery.data]);

    const repoTreeQuery = useQuery({
        queryKey: ["repo-tree", strategy?.repo_id, repoBranch],
        queryFn: () => reposApi.tree(strategy?.repo_id || "", { branch: repoBranch }),
        enabled: Boolean(strategy?.repo_id && repoBranch),
    });

    const fileTree = useMemo(() => {
        if (isRepoStrategy) {
            const paths = repoTreeQuery.data?.entries.map((entry) => entry.path) || [];
            return buildFileTreeFromPaths(paths);
        }
        const allFiles = strategyFilesQuery.data?.files || [];
        const files = showSystemFiles
            ? allFiles
            : allFiles.filter((file) => !SYSTEM_STRATEGY_FILE_PATHS.has(file.path));
        const contentByPath = Object.fromEntries(files.map((file) => [file.path, file.content]));
        return buildFileTreeFromPaths(files.map((file) => file.path), contentByPath);
    }, [isRepoStrategy, repoTreeQuery.data, strategyFilesQuery.data, showSystemFiles]);

    const allFiles = useMemo(() => getAllFiles(fileTree), [fileTree]);
    const [selectedFile, setSelectedFile] = useState<FileNode | null>(null);

    const repoFileQuery = useQuery({
        queryKey: ["repo-file", strategy?.repo_id, repoBranch, selectedFile?.path],
        queryFn: () =>
            reposApi.file(strategy?.repo_id || "", {
                branch: repoBranch,
                path: selectedFile?.path || "",
            }),
        enabled: Boolean(strategy?.repo_id && repoBranch && selectedFile?.path),
    });

    const compareQuery = useQuery({
        queryKey: ["strategy-changes-compare", compareMode, strategy?.id, strategy?.updated_at],
        queryFn: () => {
            if (!strategy) {
                return Promise.resolve({ head_commit: null, base_commit: null, subject: "", files: [] });
            }
            return isRepoStrategy
                ? strategiesApi.getGitCompare(strategy.id)
                : strategiesApi.getWorkspaceCompare(strategy.id);
        },
        enabled: Boolean(strategy && strategy.chat_status === "done"),
    });

    const changedFiles = useMemo(
        () => (compareQuery.data?.files || []).filter((file) => {
            const normalized = file.path.replace(/\\/g, "/").toLowerCase();
            return !normalized.endsWith("/overview.md") && normalized !== "overview.md" && normalized !== "strategy/overview.md";
        }),
        [compareQuery.data?.files]
    );
    const selectedChangedFile = useMemo(
        () => changedFiles.find((file) => file.path === selectedChangedPath) || null,
        [changedFiles, selectedChangedPath]
    );

    const changedFileDiffQuery = useQuery({
        queryKey: ["strategy-changes-compare-diff", compareMode, strategy?.id, strategy?.updated_at, selectedChangedPath],
        queryFn: () => {
            if (!strategy?.id || !selectedChangedPath) {
                return Promise.resolve({ path: selectedChangedPath || "", diff: "" });
            }
            return isRepoStrategy
                ? strategiesApi.getGitCompareDiff(strategy.id, selectedChangedPath)
                : strategiesApi.getWorkspaceCompareDiff(strategy.id, selectedChangedPath);
        },
        enabled: Boolean(strategy?.id && selectedChangedPath && rightPanelMode === "changes"),
    });

    const isLoading = strategyFilesQuery.isLoading || repoQuery.isLoading || repoTreeQuery.isLoading;

    useEffect(() => {
        if (allFiles.length === 0) return;
        if (!selectedFile || !allFiles.find((file) => file.path === selectedFile.path)) {
            setSelectedFile(allFiles[0]);
        }
    }, [allFiles, selectedFile]);

    useEffect(() => {
        if (!selectedChangedPath) return;
        if (!changedFiles.some((file) => file.path === selectedChangedPath)) {
            setSelectedChangedPath(changedFiles[0]?.path ?? null);
        }
    }, [changedFiles, selectedChangedPath]);

    useEffect(() => {
        setRightPanelMode("code");
        setSelectedChangedPath(null);
        setIsChangesListExpanded(true);
        setSearchQuery("");
        setActiveTab("files");
    }, [strategy?.id]);

    const handleCopy = async () => {
        const content = isRepoStrategy ? repoFileQuery.data?.content : selectedFile?.content;
        if (!content) return;
        await navigator.clipboard.writeText(content);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };


    const handleSelectFile = (node: FileNode) => {
        setSelectedFile(node);
        setRightPanelMode("code");
        if (fileDialogOpen) {
            setFileDialogOpen(false);
        }
    };

    const handleOpenCurrentChanges = () => {
        if (!isShowingChanges) {
            setIsChangesListExpanded(true);
            setRightPanelMode("changes");
            setSelectedChangedPath((previousPath) => {
                if (previousPath && changedFiles.some((file) => file.path === previousPath)) {
                    return previousPath;
                }
                return changedFiles[0]?.path ?? null;
            });
        } else {
            setIsChangesListExpanded((expanded) => !expanded);
        }
        if (fileDialogOpen) {
            setFileDialogOpen(false);
        }
    };

    const handleSelectChangedFile = (filePath: string) => {
        setRightPanelMode("changes");
        setSelectedChangedPath(filePath);
        if (fileDialogOpen) {
            setFileDialogOpen(false);
        }
    };

    const fileContent = isRepoStrategy ? repoFileQuery.data?.content : selectedFile?.content;
    const isShowingChanges = rightPanelMode === "changes";

    // Filter file tree based on search
    const filterTree = (nodes: FileNode[], query: string): FileNode[] => {
        if (!query) return nodes;
        return nodes.reduce((acc: FileNode[], node) => {
            if (node.type === "file" && node.name.toLowerCase().includes(query.toLowerCase())) {
                acc.push(node);
            } else if (node.type === "folder" && node.children) {
                const filtered = filterTree(node.children, query);
                if (filtered.length > 0) {
                    acc.push({ ...node, children: filtered });
                }
            }
            return acc;
        }, []);
    };

    const filteredTree = filterTree(fileTree, searchQuery);
    const treeToRender = activeTab === "search" ? filteredTree : fileTree;
    const compareLabel = isRepoStrategy
        ? (compareQuery.data?.head_commit
            ? t("codeView.changes.compareLabel", {
                base: shortCommit(compareQuery.data.base_commit),
                head: shortCommit(compareQuery.data.head_commit),
            })
            : t("codeView.changes.noCommit"))
        : (compareQuery.data?.base_commit
            ? t("codeView.changes.workspaceCompareLabel", {
                base: shortCommit(compareQuery.data.base_commit),
            })
            : t("codeView.changes.workspaceNoVersion"));

    const changesLoadingLabel = isRepoStrategy
        ? t("codeView.changes.loading")
        : t("codeView.changes.workspaceLoading");
    const changesEmptyListLabel = isRepoStrategy
        ? t("codeView.changes.emptyList")
        : t("codeView.changes.workspaceEmptyList");
    const changesEmptySubtitle = isRepoStrategy
        ? t("codeView.changes.emptySubtitle")
        : t("codeView.changes.workspaceEmptySubtitle");

    // Get language from file extension
    const getLanguage = (filename: string) => {
        if (filename.endsWith(".py")) return t("codeView.languages.python");
        if (filename.endsWith(".yaml") || filename.endsWith(".yml")) return t("codeView.languages.yaml");
        if (filename.endsWith(".json")) return t("codeView.languages.json");
        return t("codeView.languages.text");
    };

    // Syntax highlighting helper
    const highlightLine = (line: string, filename: string) => {
        if (filename.endsWith(".py")) {
            if (line.trim().startsWith("#")) return "text-code-comment";
            if (line.includes("def ")) return "text-code-keyword";
            if (line.includes('"""') || line.includes("'''")) return "text-code-string";
            if (line.includes("import ") || line.includes("from ")) return "text-code-meta";
            if (line.includes("return ")) return "text-code-keyword";
        }
        if (filename.endsWith(".yaml") || filename.endsWith(".yml")) {
            if (line.includes(":")) return "text-code-meta";
        }
        return "text-foreground";
    };

    if (!strategy) {
        return (
            <div className="h-full flex items-center justify-center text-muted-foreground">
                {t("codeView.selectStrategy")}
            </div>
        );
    }

    if (strategy.chat_status !== "done") {
        return (
            <div className="h-full flex items-center justify-center text-muted-foreground">
                <div className="text-center">
                    <p className="mb-2">{t("codeView.notReadyTitle")}</p>
                    <p className="text-sm">{t("codeView.notReadySubtitle")}</p>
                </div>
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                    <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    <p className="text-sm text-muted-foreground">{t("codeView.loadingFiles")}</p>
                </div>
            </div>
        );
    }

    if (isRepoStrategy && repoTreeQuery.isError) {
        return (
            <div className="h-full flex items-center justify-center text-muted-foreground">
                <div className="text-center">
                    <p className="mb-2">{t("codeView.repoNotReadyTitle")}</p>
                    <p className="text-sm">{t("codeView.repoNotReadySubtitle")}</p>
                </div>
            </div>
        );
    }

    if (fileTree.length === 0) {
        return (
            <div className="h-full flex items-center justify-center text-muted-foreground">
                <div className="text-center">
                    <p className="mb-2">
                        {isRepoStrategy ? t("codeView.emptyRepoFiles") : t("codeView.emptyStrategyFiles")}
                    </p>
                    <p className="text-sm">
                        {isRepoStrategy ? t("codeView.emptyRepoHint") : t("codeView.emptyStrategyHint")}
                    </p>
                </div>
            </div>
        );
    }

    const renderChangedFileItem = (file: StrategyGitCompareFile) => {
        const fileName = file.path.split("/").pop() || file.path;
        const isSelected = selectedChangedFile?.path === file.path && isShowingChanges;

        return (
            <button
                key={file.path}
                onClick={() => handleSelectChangedFile(file.path)}
                className={cn(
                    "w-full rounded-md border px-2 py-1.5 text-left transition-colors",
                    isSelected
                        ? "border-primary/50 bg-primary/10"
                        : "border-border bg-background hover:bg-muted/60"
                )}
            >
                <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                        <p className="truncate text-xs font-medium text-foreground">{fileName}</p>
                        <p className="truncate text-[11px] text-muted-foreground">{file.path}</p>
                    </div>
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                        {file.status}
                    </span>
                </div>
                <div className="mt-1 flex items-center gap-2 text-[11px]">
                    <span className="font-medium text-long">+{file.additions}</span>
                    <span className="font-medium text-short">-{file.deletions}</span>
                </div>
            </button>
        );
    };

    const renderChangesContent = () => {
        if (compareQuery.isLoading) {
            return (
                <div className="flex h-full items-center justify-center">
                    <div className="flex flex-col items-center gap-3">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                        <p className="text-sm text-muted-foreground">{changesLoadingLabel}</p>
                    </div>
                </div>
            );
        }

        if (compareQuery.isError) {
            return (
                <div className="flex h-full items-center justify-center text-muted-foreground">
                    <div className="text-center">
                        <p className="mb-2">{t("codeView.changes.loadError")}</p>
                    </div>
                </div>
            );
        }

        if (changedFiles.length === 0) {
            return (
                <div className="flex h-full items-center justify-center text-muted-foreground">
                    <div className="text-center">
                        <p className="mb-2">{t("codeView.changes.emptyTitle")}</p>
                        <p className="text-sm">{changesEmptySubtitle}</p>
                    </div>
                </div>
            );
        }

        if (!selectedChangedPath) {
            return (
                <div className="flex h-full items-center justify-center text-muted-foreground">
                    {t("codeView.changes.noFileSelected")}
                </div>
            );
        }

        if (changedFileDiffQuery.isLoading) {
            return (
                <div className="flex h-full items-center justify-center">
                    <div className="flex flex-col items-center gap-3">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                        <p className="text-sm text-muted-foreground">{t("codeView.changes.loadingDiff")}</p>
                    </div>
                </div>
            );
        }

        if (changedFileDiffQuery.isError) {
            return (
                <div className="flex h-full items-center justify-center text-muted-foreground">
                    {t("codeView.changes.diffError")}
                </div>
            );
        }

        return (
            <div className="h-full min-h-0 flex flex-col">
                <DiffViewer
                    filename={selectedChangedPath}
                    diffText={changedFileDiffQuery.data?.diff || ""}
                    scrollClassName="h-full min-h-0"
                />
            </div>
        );
    };

    const fileTreePanel = (
        <div className="flex h-full w-full flex-col bg-card/50">
            <div className="p-2 border-b border-border">
                <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "files" | "search")}>
                    <TabsList className="w-full">
                        <TabsTrigger value="files" className="flex-1 gap-1 text-xs">
                            <File size={12} />
                            {t("codeView.tabs.files")}
                        </TabsTrigger>
                        <TabsTrigger value="search" className="flex-1 gap-1 text-xs">
                            <Search size={12} />
                            {t("codeView.tabs.search")}
                        </TabsTrigger>
                    </TabsList>
                </Tabs>
            </div>

            {activeTab === "search" && (
                <div className="p-2 border-b border-border">
                    <div className="relative">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                        <Input
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            placeholder={t("codeView.searchPlaceholder")}
                            className="pl-9 h-8 text-sm"
                        />
                    </div>
                </div>
            )}

            <ScrollArea className="flex-1">
                <div className="space-y-3 p-2">
                    {activeTab === "files" && (
                        <div className="rounded-md border border-border bg-background p-1.5">
                            <Button
                                variant={isShowingChanges ? "secondary" : "ghost"}
                                size="sm"
                                className="w-full justify-between"
                                onClick={handleOpenCurrentChanges}
                            >
                                <span className="flex items-center gap-1.5">
                                    {isChangesListExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                    <span>{t("codeView.changes.tab")}</span>
                                </span>
                                <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                                    {changedFiles.length}
                                </span>
                            </Button>
                            {isChangesListExpanded && (
                                <div className="mt-2 space-y-1.5">
                                    {compareQuery.isLoading && (
                                        <div className="flex items-center gap-2 px-2 py-1 text-xs text-muted-foreground">
                                            <Loader2 size={12} className="animate-spin" />
                                            <span>{changesLoadingLabel}</span>
                                        </div>
                                    )}
                                    {compareQuery.isError && (
                                        <p className="px-2 py-1 text-xs text-muted-foreground">
                                            {t("codeView.changes.loadError")}
                                        </p>
                                    )}
                                    {!compareQuery.isLoading && !compareQuery.isError && changedFiles.length === 0 && (
                                        <p className="px-2 py-1 text-xs text-muted-foreground">
                                            {changesEmptyListLabel}
                                        </p>
                                    )}
                                    {!compareQuery.isLoading && !compareQuery.isError && changedFiles.map(renderChangedFileItem)}
                                </div>
                            )}
                        </div>
                    )}

                    {treeToRender.map((node, idx) => (
                        <FileTreeItem
                            key={idx}
                            node={node}
                            selectedFile={selectedFile?.path || null}
                            onSelect={handleSelectFile}
                        />
                    ))}
                    {isRepoStrategy && repoTreeQuery.data?.truncated && (
                        <p className="mt-3 text-xs text-muted-foreground">
                            {t("codeView.truncatedHint")}
                        </p>
                    )}
                </div>
            </ScrollArea>
        </div>
    );

    const mobilePanelLabel = t("codeView.tabs.files");

    return (
        <div className="h-full min-h-0 flex bg-background">
            {/* File Tree Sidebar (desktop) */}
            <div className="hidden md:flex w-64 border-r border-border">
                {fileTreePanel}
            </div>

            {/* Mobile File Tree Dialog */}
            <Dialog open={fileDialogOpen} onOpenChange={setFileDialogOpen}>
                <DialogContent className="h-[100dvh] w-[100vw] max-w-none rounded-none border-0 p-0">
                    {fileTreePanel}
                </DialogContent>
            </Dialog>

            {/* Code Panel */}
            <div className="flex-1 min-h-0 flex flex-col min-w-0">
                <div className="flex flex-col gap-2 px-4 py-3 border-b border-border bg-card/50 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                        <Button
                            variant="outline"
                            size="sm"
                            className="gap-2 md:hidden"
                            onClick={() => setFileDialogOpen(true)}
                        >
                            <Folder size={14} />
                            {mobilePanelLabel}
                        </Button>
                        <div className="flex min-w-0 flex-col">
                            <div className="flex min-w-0 items-center gap-2">
                                <File size={16} className="text-muted-foreground" />
                                <span className="truncate text-sm font-medium text-foreground">
                                    {isShowingChanges
                                        ? selectedChangedPath || t("codeView.changes.noFileSelected")
                                        : selectedFile?.path || t("codeView.noFileSelected")}
                                </span>
                                {isShowingChanges ? (
                                    <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                                        {t("codeView.changes.tab")}
                                    </span>
                                ) : (
                                    <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                                        {selectedFile ? getLanguage(selectedFile.name) : ""}
                                    </span>
                                )}
                            </div>
                            {isShowingChanges && (
                                <span className="truncate text-xs text-muted-foreground">
                                    {compareLabel}
                                </span>
                            )}
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        {!isRepoStrategy && !isShowingChanges && (
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setShowSystemFiles((prev) => !prev)}
                                className="hidden gap-2 sm:inline-flex"
                            >
                                {showSystemFiles ? <EyeOff size={14} /> : <Eye size={14} />}
                                <span>
                                    {showSystemFiles ? t("codeView.hideSystemFiles") : t("codeView.showSystemFiles")}
                                </span>
                            </Button>
                        )}
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleCopy}
                            className="hidden gap-2 sm:inline-flex"
                            disabled={!fileContent || isShowingChanges}
                        >
                            {copied ? (
                                <>
                                    <Check size={14} className="text-long" />
                                    <span>{t("common.copied")}</span>
                                </>
                            ) : (
                                <>
                                    <Copy size={14} />
                                    <span>{t("common.copy")}</span>
                                </>
                            )}
                        </Button>
                    </div>
                </div>

                <div className={cn("flex-1 min-h-0 bg-card p-4", isShowingChanges ? "overflow-hidden flex flex-col" : "overflow-auto")}>
                    {isShowingChanges ? renderChangesContent() : fileContent ? (
                        <pre className="font-mono text-[13px] leading-[1.7]">
                            <code>
                                {fileContent.split("\n").map((line, i) => (
                                    <div key={i} className="flex hover:bg-muted">
                                        <span className="mr-4 w-10 shrink-0 select-none border-r border-border pr-3 text-right text-muted-foreground">
                                            {i + 1}
                                        </span>
                                        <span className={highlightLine(line, selectedFile?.name || "")}>
                                            {line || " "}
                                        </span>
                                    </div>
                                ))}
                            </code>
                        </pre>
                    ) : (
                        <div className="flex items-center justify-center h-full text-muted-foreground">
                            {selectedFile ? t("codeView.loadingFileContent") : t("codeView.noFileSelected")}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default CodeView;
