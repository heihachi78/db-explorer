import { expect, test } from "vitest";

import { exportFilename, positionFaithfulSvg, type SvgViewSnapshot } from "./viewExport";


test("builds a vector SVG from current rendered positions with safe metadata", () => {
  const snapshot: SvgViewSnapshot = {
    title: 'Sales & Billing <current> "view"', width: 639.6, height: 479.5,
    nodes: [
      { id: "a", label: "SALES.A", x: 40, y: 50, width: 24, height: 24, shape: "diamond", fill: "#16b8c4", fillOpacity: 1, stroke: "#fff", strokeWidth: 2, textColor: "#101828", fontSize: 9 },
      { id: "b", label: "BILLING.B", x: 160, y: 100, width: 30, height: 24, shape: "round-rectangle", fill: "#ff6b35", fillOpacity: 0.5, stroke: "#d92d20", strokeWidth: 4, textColor: "#101828", fontSize: 9 },
    ],
    edges: [
      { id: "ab", source: "a", target: "b", label: "DEPENDS_ON", color: "#98a2b3", width: 1.5, opacity: 0.65, dashed: true, directed: true, fontSize: 7 },
    ],
  };
  const svg = positionFaithfulSvg(snapshot);

  expect(svg).toContain('width="640" height="480" viewBox="0 0 640 480"');
  expect(svg).toContain("Sales &amp; Billing &lt;current&gt; &quot;view&quot;");
  expect(svg).toContain('<polygon points="40,38 52,50 40,62 28,50"');
  expect(svg).toContain("<line");
  expect(svg).not.toContain('x1="40" y1="50" x2="160" y2="100"');
  expect(svg).toContain('stroke-dasharray="6 4"');
  expect(svg).toContain('marker-end="url(#arrow-0)"');
  expect(svg).not.toContain("data:image/png");
  const document = new DOMParser().parseFromString(svg, "image/svg+xml");
  expect(document.querySelector("parsererror")).toBeNull();
  expect(document.querySelectorAll("defs marker")).toHaveLength(1);
  expect(document.querySelectorAll('g[aria-label="edges"] marker')).toHaveLength(0);
});


test("normalizes a portable graph export filename", () => {
  expect(exportFilename("Értékesítés / Rendelések", "png")).toBe(
    "ertekesites-rendelesek.png",
  );
  expect(exportFilename("---", "svg")).toBe("graph-view.svg");
});
