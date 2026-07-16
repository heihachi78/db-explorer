import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { GraphEdge, GraphNode } from "../api/client";
import { GraphCanvas } from "./GraphCanvas";


const mocks = vi.hoisted(() => {
  const destroy = vi.fn();
  const graph = {
    on: vi.fn(), destroy,
    layout: vi.fn(() => ({ run: vi.fn() })),
  };
  return { create: vi.fn(() => graph), destroy };
});

vi.mock("cytoscape", () => ({ default: mocks.create }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const nodes: GraphNode[] = [{
  id: "A", owner: "SALES", name: "ORDERS", objectType: "TABLE",
  oracleObjectType: "TABLE", status: "VALID", isExternal: false, metadata: {},
}];
const edges: GraphEdge[] = [];

test("does not rebuild the graph when only selection callbacks change", () => {
  const rendered = render(
    <GraphCanvas nodes={nodes} edges={edges} onSelectNode={() => undefined} onSelectEdge={() => undefined} />,
  );
  expect(mocks.create).toHaveBeenCalledTimes(1);

  rendered.rerender(
    <GraphCanvas nodes={nodes} edges={edges} onSelectNode={vi.fn()} onSelectEdge={vi.fn()} />,
  );

  expect(mocks.create).toHaveBeenCalledTimes(1);
  expect(mocks.destroy).not.toHaveBeenCalled();
});
