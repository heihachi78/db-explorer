import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  api,
  type GraphComponent,
  type GraphEdge,
  type GraphNode,
  type GraphOverview,
  type NamedSubgraph,
  type SubgraphResult,
} from "../api/client";
import { GraphCanvas } from "./GraphCanvas";
import { EmptyGraphIllustration } from "./GraphIllustration";


const EMPTY_GRAPH: SubgraphResult = { nodes: [], edges: [], truncated: false, suggestion: null };
const TOPOLOGY_LABELS: Record<GraphComponent["topology"], string> = {
  ISOLATED: "Izolált",
  TREE: "Fa",
  CYCLIC: "Ciklusos",
};

export function GraphExplorer({
  dataVersion,
  activeSubgraph,
  onSelectSubgraph,
}: {
  dataVersion?: string | number | null;
  activeSubgraph: NamedSubgraph | null;
  onSelectSubgraph: (subgraph: NamedSubgraph | null) => void;
}) {
  const [overview, setOverview] = useState<GraphOverview | null>(null);
  const [subgraphs, setSubgraphs] = useState<NamedSubgraph[]>([]);
  const [graph, setGraph] = useState<SubgraphResult>(EMPTY_GRAPH);
  const [selectedComponents, setSelectedComponents] = useState<Set<string>>(new Set());
  const [minimumComponentSize, setMinimumComponentSize] = useState(2);
  const [componentQuery, setComponentQuery] = useState("");
  const [owner, setOwner] = useState("");
  const [objectType, setObjectType] = useState("");
  const [topology, setTopology] = useState<"ALL" | GraphComponent["topology"]>("ALL");
  const [subgraphName, setSubgraphName] = useState("");
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshSubgraphs = useCallback(async () => {
    const items = await api.subgraphs();
    setSubgraphs(items);
    return items;
  }, []);

  const loadOverview = useCallback(async () => {
    setBusy(true); setError(null);
    try {
      const result = await api.graphOverview({
        owners: owner.trim() ? [owner.trim()] : [],
        objectTypes: objectType.trim() ? [objectType.trim()] : [],
        includeExternal: true,
      });
      setOverview(result); setSelectedComponents(new Set()); setGraph(EMPTY_GRAPH);
      setSelectedNode(null); setSelectedEdge(null); onSelectSubgraph(null);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A természetes gráf nem tölthető be.");
    } finally { setBusy(false); }
  }, [objectType, onSelectSubgraph, owner]);

  useEffect(() => {
    if (!dataVersion) {
      setOverview(null); setGraph(EMPTY_GRAPH); setSubgraphs([]); return;
    }
    void Promise.all([loadOverview(), refreshSubgraphs()]);
  }, [dataVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!activeSubgraph || !dataVersion) return;
    let disposed = false;
    setBusy(true); setError(null);
    void Promise.all([api.subgraphGraph(activeSubgraph.id), api.subgraphs()]).then(([result, items]) => {
      if (disposed) return;
      setGraph(result); setSubgraphs(items); setSelectedComponents(new Set());
      setSelectedNode(null); setSelectedEdge(null);
    }).catch((reason) => {
      if (!disposed) setError(reason instanceof ApiError ? reason.message : "A részgráf nem tölthető be.");
    }).finally(() => {
      if (!disposed) setBusy(false);
    });
    return () => { disposed = true; };
  }, [activeSubgraph?.id, dataVersion]);

  const visibleComponents = useMemo(() => {
    if (!overview) return [];
    const needle = componentQuery.trim().toLocaleLowerCase("hu-HU");
    return overview.components.filter((component) => {
      if (component.nodeCount < minimumComponentSize) return false;
      if (topology !== "ALL" && component.topology !== topology) return false;
      if (!needle) return true;
      return component.sampleObjects.some((item) => item.label.toLocaleLowerCase("hu-HU").includes(needle))
        || Object.keys(component.owners).some((value) => value.toLocaleLowerCase("hu-HU").includes(needle))
        || Object.keys(component.objectTypes).some((value) => value.toLocaleLowerCase("hu-HU").includes(needle));
    });
  }, [componentQuery, minimumComponentSize, overview, topology]);

  const selectedComponentGraph = useMemo<SubgraphResult>(() => {
    if (!overview || selectedComponents.size === 0) return EMPTY_GRAPH;
    const nodes = overview.nodes.filter((node) => node.componentId && selectedComponents.has(node.componentId));
    const ids = new Set(nodes.map((node) => node.id));
    return {
      nodes,
      edges: overview.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)),
      truncated: false,
      suggestion: null,
    };
  }, [overview, selectedComponents]);

  const displayedGraph = activeSubgraph ? graph : selectedComponentGraph;

  function toggleComponent(componentId: string) {
    onSelectSubgraph(null); setGraph(EMPTY_GRAPH);
    setSelectedComponents((current) => {
      const next = new Set(current);
      if (next.has(componentId)) next.delete(componentId); else next.add(componentId);
      return next;
    });
  }

  async function createNamedSubgraph() {
    const name = subgraphName.trim();
    if (!name || selectedComponentGraph.nodes.length === 0) return;
    setBusy(true); setError(null);
    try {
      const created = await api.createSubgraph({
        name,
        objectIds: selectedComponentGraph.nodes.map((node) => node.id),
      });
      await refreshSubgraphs();
      setSubgraphName("");
      await openSubgraph(created);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A részgráf nem menthető.");
    } finally { setBusy(false); }
  }

  async function openSubgraph(item: NamedSubgraph) {
    setBusy(true); setError(null);
    try {
      const result = await api.subgraphGraph(item.id);
      setGraph(result); setSelectedComponents(new Set()); setSelectedNode(null); setSelectedEdge(null);
      onSelectSubgraph(item);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A részgráf nem tölthető be.");
    } finally { setBusy(false); }
  }

  async function removeSubgraph(item: NamedSubgraph) {
    if (!window.confirm(`Törlöd ezt a részgráfot: ${item.name}?`)) return;
    setBusy(true); setError(null);
    try {
      await api.deleteSubgraph(item.id);
      if (activeSubgraph?.id === item.id) {
        onSelectSubgraph(null); setGraph(EMPTY_GRAPH);
      }
      await refreshSubgraphs();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A részgráf nem törölhető.");
    } finally { setBusy(false); }
  }

  return (
    <section className="explorer-panel" id="graph" aria-labelledby="graph-title">
      <div className="scan-heading">
        <span className="scan-number">03</span>
        <div>
          <p className="overline">Természetes struktúra</p>
          <h3 id="graph-title">Összefüggő komponensek és részgráfok</h3>
          <p className="section-description">Szűrj, jelölj ki komponenseket, majd mentsd őket részgráfként a közösségelemzéshez.</p>
        </div>
        {activeSubgraph && <span className="explorer-root">Aktív: {activeSubgraph.name}</span>}
      </div>
      {error && <div className="error-banner" role="alert"><strong>Gráfhiba</strong><span>{error}</span></div>}

      <div className="natural-graph-controls">
        <label>Minimum elemszám<input aria-label="Minimum komponensméret" type="number" min="1" value={minimumComponentSize} onChange={(event) => setMinimumComponentSize(Math.max(1, Number(event.target.value)))} /></label>
        <label>Név vagy tartalom<input aria-label="Komponens keresése" value={componentQuery} onChange={(event) => setComponentQuery(event.target.value)} placeholder="például ORDER vagy SALES" /></label>
        <label>Séma<input aria-label="Komponens séma" value={owner} onChange={(event) => setOwner(event.target.value)} placeholder="SALES" /></label>
        <label>Objektumtípus<input aria-label="Komponens objektumtípus" value={objectType} onChange={(event) => setObjectType(event.target.value)} placeholder="TABLE" /></label>
        <label>Szerkezet<select value={topology} onChange={(event) => setTopology(event.target.value as typeof topology)}><option value="ALL">Mind</option><option value="TREE">Fa</option><option value="CYCLIC">Ciklusos</option><option value="ISOLATED">Izolált</option></select></label>
        <button type="button" onClick={() => void loadOverview()} disabled={busy || !dataVersion}>{busy ? "Frissítés…" : "Szűrés alkalmazása"}</button>
      </div>

      <div className="natural-graph-layout">
        <aside className="component-browser">
          <div className="result-count"><span>Komponensek</span><strong>{visibleComponents.length}</strong></div>
          {visibleComponents.map((component) => (
            <article key={component.id} className={selectedComponents.has(component.id) ? "active component-card" : "component-card"}>
              <label><input type="checkbox" checked={selectedComponents.has(component.id)} onChange={() => toggleComponent(component.id)} /><span>{component.id.replace("component-", "#")}</span><strong>{component.nodeCount} node · {component.edgeCount} él</strong></label>
              <small>{TOPOLOGY_LABELS[component.topology]} · {Object.keys(component.owners).slice(0, 3).join(", ")}</small>
              <p>{component.sampleObjects.map((item) => item.label).join(" · ")}</p>
              <button type="button" onClick={() => { setSelectedComponents(new Set([component.id])); onSelectSubgraph(null); }}>Csak ezt mutasd</button>
            </article>
          ))}
          {overview && visibleComponents.length === 0 && <p className="muted-copy">A szűrésnek nincs megfelelő komponens.</p>}
        </aside>

        <div className="graph-workspace">
          {displayedGraph.nodes.length > 0
            ? <GraphCanvas nodes={displayedGraph.nodes} edges={displayedGraph.edges} onSelectNode={(node) => { setSelectedNode(node); setSelectedEdge(null); }} onSelectEdge={(edge) => { setSelectedEdge(edge); setSelectedNode(null); }} />
            : <div className="graph-placeholder"><EmptyGraphIllustration /><strong>A gráf megjelenítésre kész</strong><p>Jelölj ki bal oldalt egy vagy több komponenst, vagy nyiss meg egy mentett részgráfot.</p></div>}
          {displayedGraph.truncated && <p className="graph-notice warning">{displayedGraph.suggestion}</p>}
          {selectedComponents.size > 0 && !activeSubgraph && (
            <div className="save-subgraph-bar">
              <span>{selectedComponents.size} komponens · {selectedComponentGraph.nodes.length} node</span>
              <input aria-label="Új részgráf neve" value={subgraphName} onChange={(event) => setSubgraphName(event.target.value)} placeholder="például Értékesítési mag" />
              <button type="button" className="primary-button" disabled={!subgraphName.trim() || busy} onClick={() => void createNamedSubgraph()}>Mentés részgráfként</button>
            </div>
          )}
        </div>

        <aside className="saved-subgraphs">
          <p className="overline">Mentett részgráfok</p>
          {subgraphs.length === 0 && <p className="muted-copy">A további elemzéshez mentsd el a kijelölt komponenseket.</p>}
          {subgraphs.map((item) => (
            <article key={item.id} className={activeSubgraph?.id === item.id ? "active" : ""}>
              <button type="button" onClick={() => void openSubgraph(item)}><strong>{item.name}</strong><span>{item.nodeCount} node · {item.edgeCount} él</span><small>{item.sourceKind === "COMMUNITY" ? "Közösségből" : "Komponensekből"}</small></button>
              <button type="button" aria-label={`${item.name} törlése`} onClick={() => void removeSubgraph(item)}>×</button>
            </article>
          ))}
          {(selectedNode || selectedEdge) && <div className="compact-selection-detail">{selectedNode ? <><strong>{selectedNode.owner}.{selectedNode.name}</strong><span>{selectedNode.objectType} · {selectedNode.status ?? "—"}</span></> : <><strong>{selectedEdge?.relationshipType}</strong><span>{selectedEdge?.source} → {selectedEdge?.target}</span></>}</div>}
        </aside>
      </div>
    </section>
  );
}
