import cytoscape, { type Core, type EventObject } from "cytoscape";
import { useEffect, useRef } from "react";

import type { GraphEdge, GraphNode } from "../api/client";
import { exportCurrentView, type ViewExportFormat } from "../graph/viewExport";

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onSelectNode: (node: GraphNode) => void;
  onSelectEdge: (edge: GraphEdge) => void;
}

const TYPE_COLORS: Record<string, string> = {
  TABLE: "#ff6b35",
  VIEW: "#16b8c4",
  MATERIALIZED_VIEW: "#0e9384",
  PACKAGE: "#475467",
  PROCEDURE: "#7f56d9",
  FUNCTION: "#9e77ed",
  TRIGGER: "#f79009",
  INDEX: "#98a2b3",
  EXTERNAL_OBJECT: "#d0d5dd",
};

const TYPE_SHAPES: Record<string, cytoscape.Css.NodeShape> = {
  TABLE: "round-rectangle",
  VIEW: "diamond",
  MATERIALIZED_VIEW: "hexagon",
  PACKAGE: "barrel",
  PROCEDURE: "ellipse",
  FUNCTION: "ellipse",
  TRIGGER: "triangle",
  INDEX: "rectangle",
  SYNONYM: "vee",
  EXTERNAL_OBJECT: "octagon",
};

export function GraphCanvas({ nodes, edges, onSelectNode, onSelectEdge }: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Core | null>(null);

  function exportView(format: ViewExportFormat) {
    if (graphRef.current && containerRef.current) {
      exportCurrentView(graphRef.current, containerRef.current, "Oracle object graph", format);
    }
  }

  useEffect(() => {
    if (!containerRef.current) return;
    graphRef.current?.destroy();
    const nodeMap = new Map(nodes.map((node) => [node.id, node]));
    const edgeMap = new Map(edges.map((edge) => [edge.id, edge]));
    const graph = cytoscape({
      container: containerRef.current,
      elements: [
        ...nodes.map((node) => ({
          data: {
            id: node.id,
            label: `${node.owner}.${node.name}`,
            color: TYPE_COLORS[node.objectType] ?? "#344054",
            objectType: node.objectType,
            external: node.isExternal ? "yes" : "no",
            invalid: node.status === "INVALID" ? "yes" : "no",
          },
        })),
        ...edges.map((edge) => ({
          data: {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            label: edge.relationshipType,
            confidence: edge.confidence,
          },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            shape: (element) => TYPE_SHAPES[element.data("objectType")] ?? "ellipse",
            label: "data(label)",
            color: "#101828",
            "font-size": 9,
            "text-valign": "bottom",
            "text-margin-y": 7,
            width: 24,
            height: 24,
            "border-width": 2,
            "border-color": "#ffffff",
          },
        },
        { selector: "node[external = 'yes']", style: { "background-opacity": 0.45 } },
        { selector: "node[invalid = 'yes']", style: { "border-color": "#d92d20", "border-width": 4 } },
        { selector: "node.pinned", style: { "border-color": "#16b8c4", "border-width": 4 } },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": "#98a2b3",
            "target-arrow-color": "#98a2b3",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": 7,
            color: "#667085",
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.85,
            "text-background-padding": "2px",
          },
        },
        { selector: "edge[confidence < 0.8]", style: { "line-style": "dashed", opacity: 0.65 } },
        { selector: ":selected", style: { "overlay-color": "#16b8c4", "overlay-opacity": 0.18 } },
      ],
      layout: { name: "cose", animate: false, fit: true, padding: 35 },
      minZoom: 0.15,
      maxZoom: 3,
    });
    graph.on("tap", "node", (event: EventObject) => {
      const node = nodeMap.get(event.target.id());
      if (node) onSelectNode(node);
    });
    graph.on("tap", "edge", (event: EventObject) => {
      const edge = edgeMap.get(event.target.id());
      if (edge) onSelectEdge(edge);
    });
    graph.on("cxttap", "node", (event: EventObject) => {
      const node = event.target;
      if (node.locked()) {
        node.unlock();
        node.removeClass("pinned");
      } else {
        node.lock();
        node.addClass("pinned");
      }
    });
    graphRef.current = graph;
    return () => {
      graph.destroy();
      graphRef.current = null;
    };
  }, [edges, nodes, onSelectEdge, onSelectNode]);

  return (
    <div className="graph-canvas-shell">
      <div className="graph-canvas-actions" aria-label="Aktuális objektumgráf műveletei">
        <button type="button" onClick={() => exportView("PNG")}>Aktuális nézet PNG</button>
        <button type="button" onClick={() => exportView("SVG")}>Aktuális nézet SVG</button>
        <button
          type="button"
          title="A jobb kattintással rögzített node-ok a helyükön maradnak."
          onClick={() => graphRef.current?.layout({ name: "cose", animate: false, fit: true, padding: 35 }).run()}
        >Elrendezés újrafuttatása</button>
      </div>
      <div className="graph-canvas" ref={containerRef} aria-label="Objektumgráf" />
    </div>
  );
}
