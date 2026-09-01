import React, { useEffect, useMemo, useRef } from "react";
import { Graph } from "@antv/g6";

export interface WorkflowNode {
  id: string;
  label?: string;
  type?: string;
}

export interface WorkflowEdge {
  id?: string;
  source: string;
  target: string;
  label?: string;
  weight?: number;
}

export interface WorkflowGraphData {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

interface StrategyWorkflowGraphProps {
  data?: WorkflowGraphData;
  height?: number;
  animate?: boolean;
}

function clampEdgeWidth(weight: number | undefined): number {
  if (!Number.isFinite(weight)) return 2;
  return Math.max(1.5, Math.min(8, Number(weight)));
}

function nodeColors(type: string | undefined): { fill: string; stroke: string } {
  const normalized = (type || "").toLowerCase();
  if (normalized === "start") return { fill: "#E6FFFB", stroke: "#13C2C2" };
  if (normalized === "end") return { fill: "#FFF1F0", stroke: "#FF4D4F" };
  if (normalized === "decision") return { fill: "#FFF7E6", stroke: "#FA8C16" };
  if (normalized === "action") return { fill: "#F6FFED", stroke: "#52C41A" };
  if (normalized === "reason") return { fill: "#F9F0FF", stroke: "#9254DE" };
  return { fill: "#EFF4FF", stroke: "#5B8FF9" };
}

const StrategyWorkflowGraph: React.FC<StrategyWorkflowGraphProps> = ({ data, height = 500, animate = false }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);
  const animationTimerRef = useRef<number | null>(null);

  const normalizedData = useMemo<WorkflowGraphData | null>(() => {
    if (!data?.nodes?.length) return null;
    const nodes = data.nodes.map((node) => ({
      id: String(node.id),
      label: node.label || node.id,
      type: node.type || "process",
    }));

    const edges = (data.edges || []).map((edge, index) => {
      const source = String(edge.source);
      const target = String(edge.target);
      return {
        id: edge.id || `edge-${index}-${source}-${target}`,
        source,
        target,
        label: edge.label || "",
        weight: Number(edge.weight || 0),
      };
    });

    return { nodes, edges };
  }, [data]);

  useEffect(() => {
    if (!containerRef.current || !normalizedData) return;
    let disposed = false;

    if (animationTimerRef.current) {
      window.clearInterval(animationTimerRef.current);
      animationTimerRef.current = null;
    }

    if (graphRef.current) {
      graphRef.current.destroy();
      graphRef.current = null;
    }

    const graph = new Graph({
      container: containerRef.current,
      width: containerRef.current.clientWidth,
      height,
      autoResize: true,
      animation: true,
      data: {
        nodes: normalizedData.nodes.map((node) => {
          const palette = nodeColors(node.type);
          return {
            id: node.id,
            data: {
              label: node.label,
              type: node.type,
            },
            style: {
              labelText: node.label,
              labelPlacement: "center",
              fill: palette.fill,
              stroke: palette.stroke,
              lineWidth: 1.5,
              radius: 8,
              size: [130, 46],
            },
          };
        }),
        edges: normalizedData.edges.map((edge) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          data: {
            label: edge.label,
            weight: edge.weight,
          },
          style: {
            labelText: edge.label,
            stroke: "#94A3B8",
            endArrow: true,
            lineWidth: clampEdgeWidth(edge.weight),
            opacity: 0.9,
          },
        })),
      },
      node: {
        state: {
          active: {
            lineWidth: 3,
            stroke: "#1677FF",
            shadowBlur: 12,
            shadowColor: "rgba(22, 119, 255, 0.35)",
          },
        },
      },
      edge: {
        type: "polyline",
        state: {
          active: {
            stroke: "#1677FF",
            lineWidth: 4,
            opacity: 1,
          },
        },
      },
      transforms: [
        {
          type: "process-parallel-edges",
          mode: "bundle",
          distance: 12,
        },
      ],
      layout: {
        type: "antv-dagre",
        rankdir: "LR",
        nodesep: 26,
        ranksep: 54,
      },
      behaviors: ["drag-canvas", "zoom-canvas", "drag-element"],
    });

    const start = async () => {
      try {
        await graph.render();
      } catch {
        return;
      }
      if (disposed) {
        graph.destroy();
        return;
      }
      graphRef.current = graph;

      if (animate && normalizedData.edges.length > 0) {
        const edgeById = new Map(normalizedData.edges.map((edge) => [edge.id, edge]));
        const edgeIds = normalizedData.edges.map((edge) => edge.id).filter(Boolean) as string[];
        let index = 0;
        let prevEdgeId: string | null = null;
        let prevNodes: string[] = [];

        const tick = () => {
          if (disposed || graphRef.current !== graph || edgeIds.length === 0) return;
          const nextEdgeId = edgeIds[index % edgeIds.length];
          index += 1;
          const nextEdge = edgeById.get(nextEdgeId);
          const nextNodes = nextEdge ? [nextEdge.source, nextEdge.target] : [];

          const nextState: Record<string, string[]> = {};
          if (prevEdgeId) nextState[prevEdgeId] = [];
          for (const nodeId of prevNodes) nextState[nodeId] = [];
          nextState[nextEdgeId] = ["active"];
          for (const nodeId of nextNodes) nextState[nodeId] = ["active"];

          void graph.setElementState(nextState, false).catch(() => {
            // Ignore transient state update errors during graph lifecycle transitions.
          });
          prevEdgeId = nextEdgeId;
          prevNodes = nextNodes;
        };

        tick();
        animationTimerRef.current = window.setInterval(tick, 1100);
      }
    };

    void start();

    return () => {
      disposed = true;
      if (animationTimerRef.current) {
        window.clearInterval(animationTimerRef.current);
        animationTimerRef.current = null;
      }
      if (graphRef.current) {
        graphRef.current.destroy();
        graphRef.current = null;
      }
    };
  }, [normalizedData, height, animate]);

  if (!normalizedData || normalizedData.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground border border-dashed rounded-lg" style={{ height }}>
        No workflow data available
      </div>
    );
  }

  return <div ref={containerRef} className="w-full border rounded-lg overflow-hidden bg-card" style={{ height }} />;
};

export default StrategyWorkflowGraph;
