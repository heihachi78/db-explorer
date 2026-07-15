import type { Core, NodeSingular } from "cytoscape";


export type ViewExportFormat = "PNG" | "SVG";

export interface SvgViewNode {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  shape: string;
  fill: string;
  fillOpacity: number;
  stroke: string;
  strokeWidth: number;
  textColor: string;
  fontSize: number;
}

export interface SvgViewEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  color: string;
  width: number;
  opacity: number;
  dashed: boolean;
  directed: boolean;
  fontSize: number;
}

export interface SvgViewSnapshot {
  title: string;
  width: number;
  height: number;
  nodes: SvgViewNode[];
  edges: SvgViewEdge[];
}

function escapeXml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function numericStyle(value: string, fallback: number) {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function exportFilename(baseName: string, extension: string) {
  const slug = baseName
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${slug || "graph-view"}.${extension}`;
}

function polygonPoints(node: SvgViewNode, unitPoints: Array<[number, number]>) {
  return unitPoints
    .map(([x, y]) => `${node.x + x * node.width / 2},${node.y + y * node.height / 2}`)
    .join(" ");
}

function nodeShape(node: SvgViewNode) {
  const common = `fill="${escapeXml(node.fill)}" fill-opacity="${node.fillOpacity}" stroke="${escapeXml(node.stroke)}" stroke-width="${node.strokeWidth}"`;
  if (["rectangle", "roundrectangle", "round-rectangle", "barrel"].includes(node.shape)) {
    const radius = node.shape === "rectangle" ? 0 : Math.min(node.width, node.height) * 0.22;
    return `<rect x="${node.x - node.width / 2}" y="${node.y - node.height / 2}" width="${node.width}" height="${node.height}" rx="${radius}" ${common}/>`;
  }
  const polygon: Record<string, Array<[number, number]>> = {
    diamond: [[0, -1], [1, 0], [0, 1], [-1, 0]],
    triangle: [[0, -1], [1, 1], [-1, 1]],
    hexagon: [[-0.5, -1], [0.5, -1], [1, 0], [0.5, 1], [-0.5, 1], [-1, 0]],
    octagon: [[-0.42, -1], [0.42, -1], [1, -0.42], [1, 0.42], [0.42, 1], [-0.42, 1], [-1, 0.42], [-1, -0.42]],
    vee: [[-1, -1], [0, 0.35], [1, -1], [0, 1]],
  };
  if (polygon[node.shape]) {
    return `<polygon points="${polygonPoints(node, polygon[node.shape])}" ${common}/>`;
  }
  return `<ellipse cx="${node.x}" cy="${node.y}" rx="${node.width / 2}" ry="${node.height / 2}" ${common}/>`;
}

function edgeEndpoint(from: SvgViewNode, to: SvgViewNode, entering: boolean) {
  const deltaX = to.x - from.x;
  const deltaY = to.y - from.y;
  const length = Math.hypot(deltaX, deltaY) || 1;
  const node = entering ? to : from;
  const radius = Math.min(node.width, node.height) / 2 + node.strokeWidth / 2;
  const direction = entering ? -1 : 1;
  return {
    x: node.x + direction * deltaX / length * radius,
    y: node.y + direction * deltaY / length * radius,
  };
}

export function positionFaithfulSvg(snapshot: SvgViewSnapshot) {
  const width = Math.max(1, Math.round(snapshot.width));
  const height = Math.max(1, Math.round(snapshot.height));
  const nodeById = new Map(snapshot.nodes.map((node) => [node.id, node]));
  const edgeMarkup = snapshot.edges.flatMap((edge, index) => {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (!source || !target) return [];
    const start = edgeEndpoint(source, target, false);
    const end = edgeEndpoint(source, target, true);
    const marker = edge.directed ? ` marker-end="url(#arrow-${index})"` : "";
    const dash = edge.dashed ? ' stroke-dasharray="6 4"' : "";
    const middleX = (source.x + target.x) / 2;
    const middleY = (source.y + target.y) / 2;
    return [
      edge.directed
        ? `<marker id="arrow-${index}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="${escapeXml(edge.color)}"/></marker>`
        : "",
      `<line x1="${start.x}" y1="${start.y}" x2="${end.x}" y2="${end.y}" stroke="${escapeXml(edge.color)}" stroke-width="${edge.width}" stroke-opacity="${edge.opacity}"${dash}${marker}/>`,
      edge.label
        ? `<text x="${middleX}" y="${middleY - 4}" text-anchor="middle" font-family="system-ui, sans-serif" font-size="${edge.fontSize}" fill="#667085" paint-order="stroke" stroke="#ffffff" stroke-width="3">${escapeXml(edge.label)}</text>`
        : "",
    ];
  }).join("\n  ");
  const nodeMarkup = snapshot.nodes.map((node) => [
    nodeShape(node),
    `<text x="${node.x}" y="${node.y + node.height / 2 + node.fontSize + 5}" text-anchor="middle" font-family="system-ui, sans-serif" font-size="${node.fontSize}" fill="${escapeXml(node.textColor)}">${escapeXml(node.label)}</text>`,
  ].join("\n  ")).join("\n  ");
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`,
    `  <title>${escapeXml(snapshot.title)}</title>`,
    "  <desc>Vector capture using the current interactive graph viewport and rendered node positions.</desc>",
    `  <rect width="${width}" height="${height}" fill="#ffffff"/>`,
    `  <defs>${edgeMarkup.includes("<marker") ? edgeMarkup.match(/<marker[\s\S]*?<\/marker>/g)?.join("") ?? "" : ""}</defs>`,
    `  <g aria-label="edges">${edgeMarkup.replace(/<marker[\s\S]*?<\/marker>/g, "")}</g>`,
    `  <g aria-label="nodes">${nodeMarkup}</g>`,
    "</svg>",
  ].join("\n");
}

function graphSnapshot(graph: Core, container: HTMLElement, title: string): SvgViewSnapshot {
  const nodes = graph.nodes().map((node: NodeSingular): SvgViewNode => {
    const position = node.renderedPosition();
    return {
      id: node.id(),
      label: String(node.data("label") ?? ""),
      x: position.x,
      y: position.y,
      width: node.renderedWidth(),
      height: node.renderedHeight(),
      shape: String(node.style("shape")),
      fill: String(node.style("background-color")),
      fillOpacity: numericStyle(String(node.style("background-opacity")), 1),
      stroke: String(node.style("border-color")),
      strokeWidth: numericStyle(String(node.style("border-width")), 0),
      textColor: String(node.style("color")),
      fontSize: numericStyle(String(node.style("font-size")), 10),
    };
  });
  const edges = graph.edges().map((edge): SvgViewEdge => ({
    id: edge.id(),
    source: edge.source().id(),
    target: edge.target().id(),
    label: String(edge.data("label") ?? ""),
    color: String(edge.style("line-color")),
    width: numericStyle(String(edge.style("width")), 1),
    opacity: numericStyle(String(edge.style("opacity")), 1),
    dashed: String(edge.style("line-style")) === "dashed",
    directed: String(edge.style("target-arrow-shape")) !== "none",
    fontSize: numericStyle(String(edge.style("font-size")), 8),
  }));
  return { title, width: container.clientWidth, height: container.clientHeight, nodes, edges };
}

function downloadHref(href: string, filename: string, revoke = false) {
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  anchor.hidden = true;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  if (revoke) window.setTimeout(() => URL.revokeObjectURL(href), 0);
}

export function exportCurrentView(
  graph: Core,
  container: HTMLElement,
  baseName: string,
  format: ViewExportFormat,
) {
  if (format === "PNG") {
    downloadHref(
      graph.png({ output: "base64uri", full: false, scale: 2, bg: "#ffffff" }),
      exportFilename(baseName, "png"),
    );
    return;
  }
  const svg = positionFaithfulSvg(graphSnapshot(graph, container, baseName));
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }));
  downloadHref(url, exportFilename(baseName, "svg"), true);
}
