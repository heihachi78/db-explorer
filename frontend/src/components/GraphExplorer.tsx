import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import {
  ApiError,
  api,
  type GraphComponent,
  type GraphEdge,
  type GraphNode,
  type GraphOverview,
  type ObjectSearchResult,
  type SubgraphResult,
} from "../api/client";
import { GraphCanvas } from "./GraphCanvas";

const EMPTY_GRAPH: SubgraphResult = {
  rootObjectIds: [], nodes: [], edges: [], truncated: false, suggestion: null,
};

const TOPOLOGY_LABELS: Record<GraphComponent["topology"], string> = {
  ISOLATED: "Izolált",
  TREE: "Fa",
  CYCLIC: "Ciklusos",
};

interface GraphExplorerProps {
  dataVersion?: string | null;
}

export function GraphExplorer({ dataVersion = null }: GraphExplorerProps) {
  const [query, setQuery] = useState("");
  const [owner, setOwner] = useState("");
  const [objectType, setObjectType] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState<ObjectSearchResult | null>(null);
  const [graph, setGraph] = useState<SubgraphResult>(EMPTY_GRAPH);
  const [overview, setOverview] = useState<GraphOverview | null>(null);
  const [mode, setMode] = useState<"OVERVIEW" | "SEARCH">("OVERVIEW");
  const [selectedComponents, setSelectedComponents] = useState<Set<string>>(new Set());
  const [componentQuery, setComponentQuery] = useState("");
  const [minimumComponentSize, setMinimumComponentSize] = useState(1);
  const [componentTopology, setComponentTopology] = useState<"ALL" | GraphComponent["topology"]>("ALL");
  const [root, setRoot] = useState<GraphNode | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [depth, setDepth] = useState(1);
  const [direction, setDirection] = useState<"INCOMING" | "OUTGOING" | "BOTH">("BOTH");
  const [relationshipTypes, setRelationshipTypes] = useState("");
  const [minimumConfidence, setMinimumConfidence] = useState(0);
  const [includeExternal, setIncludeExternal] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysisNote, setAnalysisNote] = useState<string | null>(null);

  const selectNode = useCallback((node: GraphNode) => {
    setSelectedNode(node);
    setSelectedEdge(null);
  }, []);
  const selectEdge = useCallback((edge: GraphEdge) => {
    setSelectedEdge(edge);
    setSelectedNode(null);
  }, []);

  async function run<T>(operation: () => Promise<T>, accept: (value: T) => void) {
    setBusy(true);
    setError(null);
    try {
      accept(await operation());
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A gráfművelet váratlan hibával leállt.");
    } finally {
      setBusy(false);
    }
  }

  function parsedRelationshipTypes() {
    return relationshipTypes.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean);
  }

  function graphFilters() {
    return {
      relationshipTypes: parsedRelationshipTypes(),
      minimumConfidence,
      includeExternal,
    };
  }

  function loadOverview() {
    setMode("OVERVIEW");
    setRoot(null);
    setAnalysisNote(null);
    void run(
      () => api.graphOverview({
        owners: owner ? [owner.trim().toUpperCase()] : [],
        objectTypes: objectType ? [objectType.trim().toUpperCase()] : [],
        statuses: status ? [status.trim().toUpperCase()] : [],
        ...graphFilters(),
      }),
      (result) => {
        if (!Array.isArray(result.components) || !Array.isArray(result.nodes)) return;
        setOverview(result);
        setSelectedComponents(new Set());
        setSelectedNode(null);
        setSelectedEdge(null);
      },
    );
  }

  useEffect(() => {
    if (dataVersion) loadOverview();
    // A verzió csak egy sikeresen publikált új forrásgráfnál változik.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataVersion]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setMode("SEARCH");
    void run(
      () => api.searchObjects({ q: query, owner, objectType, status, pageSize: 30 }),
      setSearch,
    );
  }

  function showSubgraph(node: GraphNode) {
    setMode("SEARCH");
    setRoot(node);
    setAnalysisNote(null);
    void run(
      () => api.subgraph({ rootObjectIds: [node.id], depth, direction, ...graphFilters() }),
      (result) => {
        setGraph(result);
        setSelectedNode(node);
        setSelectedEdge(null);
      },
    );
  }

  function refreshSubgraph() {
    if (root) showSubgraph(root);
  }

  function showImpact(impactMode: "DEPENDENTS" | "DEPENDENCIES") {
    const node = selectedNode ?? root;
    if (!node) return;
    setMode("SEARCH");
    void run(
      () => api.impact({ objectId: node.id, mode: impactMode, maxDepth: 5, ...graphFilters() }),
      (result) => {
        setGraph(result);
        setRoot(node);
        setAnalysisNote(impactMode === "DEPENDENTS"
          ? "Becsült hatás: az objektumtól közvetlenül vagy közvetve függő elemek."
          : "Függőségek: az objektum által közvetlenül vagy közvetve használt elemek.");
      },
    );
  }

  function showPath(target: GraphNode, pathMode: "HOPS" | "WEIGHTED") {
    if (!root || root.id === target.id) return;
    void run(
      () => api.paths({
        sourceId: root.id, targetId: target.id, mode: pathMode, directed: false, maxPaths: 1,
        ...graphFilters(),
      }),
      (result) => {
        const path = result.paths[0];
        if (!path) {
          setError("A két objektum között a beállított korlátokon belül nincs útvonal.");
          return;
        }
        setGraph({
          rootObjectIds: [root.id, target.id], nodes: path.nodes, edges: path.edges,
          truncated: result.truncated, suggestion: null,
        });
        setAnalysisNote(`${pathMode === "HOPS" ? "Legrövidebb" : "Legrelevánsabb"} útvonal: ${path.hops} lépés.`);
      },
    );
  }

  const visibleComponents = useMemo(() => {
    if (!overview) return [];
    const needle = componentQuery.trim().toLocaleLowerCase("hu-HU");
    const labelsByComponent = new Map<string, string[]>();
    for (const node of overview.nodes) {
      if (!node.componentId) continue;
      const labels = labelsByComponent.get(node.componentId) ?? [];
      labels.push(`${node.owner}.${node.name}`, node.objectType);
      labelsByComponent.set(node.componentId, labels);
    }
    return overview.components.filter((component) => (
      component.nodeCount >= minimumComponentSize
      && (componentTopology === "ALL" || component.topology === componentTopology)
      && (!needle || (labelsByComponent.get(component.id) ?? []).some((label) => label.toLocaleLowerCase("hu-HU").includes(needle)))
    ));
  }, [componentQuery, componentTopology, minimumComponentSize, overview]);

  const displayedOverviewGraph = useMemo<SubgraphResult>(() => {
    if (!overview) return EMPTY_GRAPH;
    const componentIds = selectedComponents.size
      ? selectedComponents
      : new Set(visibleComponents.map((component) => component.id));
    const nodes = overview.nodes.filter((node) => node.componentId && componentIds.has(node.componentId));
    const nodeIds = new Set(nodes.map((node) => node.id));
    return {
      rootObjectIds: [],
      nodes,
      edges: overview.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)),
      truncated: false,
      suggestion: null,
    };
  }, [overview, selectedComponents, visibleComponents]);

  const displayedGraph = mode === "OVERVIEW" ? displayedOverviewGraph : graph;

  function toggleComponent(componentId: string) {
    setSelectedComponents((current) => {
      const next = new Set(current);
      if (next.has(componentId)) next.delete(componentId);
      else next.add(componentId);
      return next;
    });
  }

  return (
    <section className="explorer-panel">
      <div className="scan-heading">
        <span className="scan-number">03</span>
        <div><p className="overline">Gráfböngésző</p><h3>Teljes térkép és interaktív feltárás</h3></div>
        <div className="explorer-mode-actions">
          <button type="button" className={mode === "OVERVIEW" ? "active" : ""} onClick={loadOverview} disabled={busy}>Teljes térkép</button>
          <button type="button" className={mode === "SEARCH" ? "active" : ""} onClick={() => setMode("SEARCH")}>Objektumkeresés</button>
        </div>
        {root && mode === "SEARCH" && <span className="explorer-root">{root.owner}.{root.name}</span>}
      </div>

      <form className="object-search" onSubmit={submitSearch}>
        <label>
          <span>Objektumnév vagy stabil ID</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="például ORDER*" />
        </label>
        <label><span>Owner</span><input value={owner} onChange={(event) => setOwner(event.target.value)} placeholder="SALES" /></label>
        <label><span>Típus</span><input value={objectType} onChange={(event) => setObjectType(event.target.value)} placeholder="TABLE" /></label>
        <label><span>Állapot</span><input value={status} onChange={(event) => setStatus(event.target.value)} placeholder="VALID" /></label>
        <button className="primary-button" disabled={busy}>Keresés</button>
      </form>

      {overview && mode === "OVERVIEW" && (
        <div className="overview-summary" aria-label="Teljes gráf összesítése">
          <div><span>Megjelenített node</span><strong>{displayedGraph.nodes.length.toLocaleString("hu-HU")}</strong></div>
          <div><span>Megjelenített él</span><strong>{displayedGraph.edges.length.toLocaleString("hu-HU")}</strong></div>
          <div><span>Összefüggő komponens</span><strong>{overview.summary.componentCount.toLocaleString("hu-HU")}</strong></div>
          <div><span>Fa / ciklusos / izolált</span><strong>{overview.summary.treeComponentCount} / {overview.summary.cyclicComponentCount} / {overview.summary.isolatedNodeCount}</strong></div>
        </div>
      )}
      {error && <div className="error-banner" role="alert"><strong>Gráfhiba</strong><span>{error}</span></div>}

      <div className="explorer-layout">
        <aside className="search-results">
          {mode === "OVERVIEW" ? (
            <>
              <div className="result-count"><span>Komponensek</span><strong>{visibleComponents.length}</strong></div>
              <div className="component-filters">
                <label>Keresés a komponensekben<input value={componentQuery} onChange={(event) => setComponentQuery(event.target.value)} placeholder="owner, objektum, típus" /></label>
                <label>Legalább ennyi node<input type="number" min="1" value={minimumComponentSize} onChange={(event) => setMinimumComponentSize(Math.max(1, Number(event.target.value)))} /></label>
                <label>Szerkezet<select value={componentTopology} onChange={(event) => setComponentTopology(event.target.value as typeof componentTopology)}><option value="ALL">Mind</option><option value="TREE">Fa</option><option value="CYCLIC">Ciklusos</option><option value="ISOLATED">Izolált</option></select></label>
                <button type="button" onClick={loadOverview}>Owner / típus / állapot alkalmazása</button>
                <button type="button" onClick={() => setSelectedComponents(new Set())}>Teljes szűrt halmaz</button>
              </div>
              {visibleComponents.map((component) => (
                <article key={component.id} className={selectedComponents.has(component.id) ? "active component-card" : "component-card"}>
                  <label>
                    <input type="checkbox" checked={selectedComponents.has(component.id)} onChange={() => toggleComponent(component.id)} />
                    <span>{component.id.replace("component-", "#")}</span>
                    <strong>{component.nodeCount} node · {component.edgeCount} él</strong>
                  </label>
                  <small>{TOPOLOGY_LABELS[component.topology]} · {Object.keys(component.owners).slice(0, 2).join(", ") || "owner nélkül"}</small>
                  <p>{component.sampleObjects.map((item) => item.label).join(" · ")}</p>
                  <button type="button" onClick={() => setSelectedComponents(new Set([component.id]))}>Csak ezt mutasd</button>
                </article>
              ))}
              {!overview && <p className="muted-copy">Töltsd be a teljes térképet.</p>}
            </>
          ) : (
            <>
              <div className="result-count"><span>Találatok</span><strong>{search?.total ?? 0}</strong></div>
              {!search && <p className="muted-copy">Keress név, owner vagy objektumtípus alapján.</p>}
              {search?.items.map((node) => (
                <article key={node.id} className={root?.id === node.id ? "active" : ""}>
                  <span>{node.objectType}</span><strong>{node.owner}.{node.name}</strong>
                  <div>
                    <button type="button" onClick={() => showSubgraph(node)}>Gráf</button>
                    {root && root.id !== node.id && <><button type="button" onClick={() => showPath(node, "HOPS")}>Rövid út</button><button type="button" onClick={() => showPath(node, "WEIGHTED")}>Releváns út</button></>}
                  </div>
                </article>
              ))}
            </>
          )}
        </aside>

        <div className="graph-workspace">
          <div className="graph-toolbar">
            {mode === "SEARCH" && <>
              <label>Mélység<select value={depth} onChange={(event) => setDepth(Number(event.target.value))}><option value={1}>1</option><option value={2}>2</option><option value={3}>3</option></select></label>
              <label>Irány<select value={direction} onChange={(event) => setDirection(event.target.value as typeof direction)}><option value="BOTH">Mindkettő</option><option value="OUTGOING">Kimenő</option><option value="INCOMING">Bejövő</option></select></label>
            </>}
            <label>Kapcsolattípusok<input aria-label="Kapcsolattípusok" value={relationshipTypes} onChange={(event) => setRelationshipTypes(event.target.value)} placeholder="DEPENDS_ON, FOREIGN_KEY" /></label>
            <label>Min. confidence<input aria-label="Minimum confidence" type="number" min="0" max="1" step="0.05" value={minimumConfidence} onChange={(event) => setMinimumConfidence(Number(event.target.value))} /></label>
            <label className="graph-filter-check"><input aria-label="Külső objektumok" type="checkbox" checked={includeExternal} onChange={(event) => setIncludeExternal(event.target.checked)} />Külső objektumok</label>
            {mode === "OVERVIEW"
              ? <button type="button" onClick={loadOverview} disabled={busy}>Térkép frissítése</button>
              : <button type="button" onClick={refreshSubgraph} disabled={!root || busy}>Újratöltés</button>}
            <button type="button" onClick={() => showImpact("DEPENDENTS")} disabled={(!root && !selectedNode) || busy}>Hatás</button>
            <button type="button" onClick={() => showImpact("DEPENDENCIES")} disabled={(!root && !selectedNode) || busy}>Függőségek</button>
          </div>
          {displayedGraph.nodes.length ? (
            <GraphCanvas nodes={displayedGraph.nodes} edges={displayedGraph.edges} onSelectNode={selectNode} onSelectEdge={selectEdge} />
          ) : (
            <div className="graph-placeholder"><span>⌘</span><p>{mode === "OVERVIEW" ? "Töltsd be a teljes térképet, vagy lazíts a komponensszűrésen." : "Nyiss meg egy keresési találatot a részgráf megjelenítéséhez."}</p></div>
          )}
          {mode === "SEARCH" && (graph.truncated || analysisNote) && <div className={graph.truncated ? "graph-notice warning" : "graph-notice"}>{graph.truncated ? graph.suggestion ?? "Az eredmény elérte a szerveroldali limitet." : analysisNote}</div>}
        </div>

        <aside className="detail-panel">
          <p className="overline">Kijelölt elem</p>
          {selectedNode && <><h4>{selectedNode.owner}.{selectedNode.name}</h4><dl><div><dt>Típus</dt><dd>{selectedNode.objectType}</dd></div><div><dt>Állapot</dt><dd>{selectedNode.status ?? "—"}</dd></div>{selectedNode.componentId && <div><dt>Komponens</dt><dd>{selectedNode.componentId.replace("component-", "#")}</dd></div>}<div><dt>Mélység</dt><dd>{selectedNode.depth ?? 0}</dd></div><div><dt>Külső</dt><dd>{selectedNode.isExternal ? "igen" : "nem"}</dd></div></dl><code>{selectedNode.id}</code></>}
          {selectedEdge && <><h4>{selectedEdge.relationshipType}</h4><dl><div><dt>Irány</dt><dd>{selectedEdge.directed ? "irányított" : "irányítatlan"}</dd></div><div><dt>Confidence</dt><dd>{selectedEdge.confidence.toFixed(2)}</dd></div>{selectedEdge.effectiveWeight !== undefined && <div><dt>Effektív súly</dt><dd>{selectedEdge.effectiveWeight.toFixed(3)}</dd></div>}{selectedEdge.stepCost !== undefined && <div><dt>Lépésköltség</dt><dd>{selectedEdge.stepCost.toFixed(3)}</dd></div>}<div><dt>Forrás</dt><dd>{selectedEdge.origin}</dd></div></dl><h5>Evidence</h5>{selectedEdge.evidence.length ? selectedEdge.evidence.map((item, index) => <pre key={`${item.sourceView}-${index}`}>{item.sourceView}{"\n"}{JSON.stringify(item.details, null, 2)}</pre>) : <p className="muted-copy">Nincs külön evidence rekord.</p>}</>}
          {!selectedNode && !selectedEdge && <p className="muted-copy">Kattints egy node-ra vagy élre.</p>}
        </aside>
      </div>
    </section>
  );
}
