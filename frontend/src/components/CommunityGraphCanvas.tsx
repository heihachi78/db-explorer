import cytoscape, { type Core, type EventObject } from "cytoscape";
import { useEffect, useRef } from "react";

import type { CommunityGraph } from "../api/client";


export function CommunityGraphCanvas({
  graph,
  onSelectCommunity,
}: {
  graph: CommunityGraph;
  onSelectCommunity: (communityId: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Core | null>(null);

  function rerunLayout() {
    graphRef.current?.layout({ name: "cose", animate: false, fit: true, padding: 45 }).run();
  }

  useEffect(() => {
    if (!containerRef.current) return;
    if (navigator.userAgent.toLowerCase().includes("jsdom")) return;
    graphRef.current?.destroy();
    const instance = cytoscape({
      container: containerRef.current,
      elements: [
        ...graph.nodes.map((community) => ({
          data: {
            id: `community-${community.communityId}`,
            communityId: community.communityId,
            label: community.annotation?.name ?? community.suggestedName,
            nodeCount: community.nodeCount,
            size: Math.max(38, Math.min(92, 28 + Math.sqrt(community.nodeCount) * 8)),
            schema: community.dominantSchema,
            stability: community.stability,
          },
        })),
        ...graph.edges.map((edge) => ({
          data: {
            id: `community-edge-${edge.sourceCommunity}-${edge.targetCommunity}`,
            source: `community-${edge.sourceCommunity}`,
            target: `community-${edge.targetCommunity}`,
            label: `${edge.edgeCount} él · ${edge.totalWeight.toFixed(1)}`,
            width: Math.max(1.5, Math.min(9, Math.sqrt(edge.totalWeight))),
          },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            width: "data(size)", height: "data(size)", label: "data(label)",
            "background-color": "#1d3557", "border-color": "#e76f51", "border-width": 3,
            color: "#101828", "font-size": 10, "font-weight": "bold",
            "text-valign": "bottom", "text-margin-y": 8,
            "text-wrap": "wrap", "text-max-width": "125px",
          },
        },
        { selector: "node[stability = 'STABLE']", style: { "border-color": "#12b76a" } },
        { selector: "node[stability = 'UNSTABLE']", style: { "border-color": "#f04438", "border-style": "double" } },
        {
          selector: "edge",
          style: {
            width: "data(width)", "line-color": "#98a2b3", "curve-style": "bezier",
            label: "data(label)", color: "#667085", "font-size": 8,
            "text-background-color": "#ffffff", "text-background-opacity": 0.9,
            "text-background-padding": "3px",
          },
        },
        { selector: ":selected", style: { "overlay-color": "#16b8c4", "overlay-opacity": 0.18 } },
      ],
      layout: { name: "cose", animate: false, fit: true, padding: 45 },
      minZoom: 0.2,
      maxZoom: 3,
    });
    instance.on("tap", "node", (event: EventObject) => {
      onSelectCommunity(Number(event.target.data("communityId")));
    });
    graphRef.current = instance;
    return () => {
      instance.destroy();
      graphRef.current = null;
    };
  }, [graph, onSelectCommunity]);

  return (
    <div className="community-map-wrap">
      <button type="button" onClick={rerunLayout}>Elrendezés újrafuttatása</button>
      <div className="community-map-canvas" ref={containerRef} aria-label="Aggregált közösségi gráf" />
    </div>
  );
}
