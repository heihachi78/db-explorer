import { useCallback, useState, type FormEvent } from "react";

import {
  ApiError,
  api,
  type GraphEdge,
  type GraphNode,
  type ObjectSearchResult,
  type SubgraphResult,
} from "../api/client";
import { GraphCanvas } from "./GraphCanvas";

const EMPTY_GRAPH: SubgraphResult = {
  rootObjectIds: [], nodes: [], edges: [], truncated: false, suggestion: null,
};

export function GraphExplorer() {
  const [query, setQuery] = useState("");
  const [owner, setOwner] = useState("");
  const [objectType, setObjectType] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState<ObjectSearchResult | null>(null);
  const [graph, setGraph] = useState<SubgraphResult>(EMPTY_GRAPH);
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

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    void run(
      () => api.searchObjects({ q: query, owner, objectType, status, pageSize: 30 }),
      setSearch,
    );
  }

  function graphFilters() {
    return {
      relationshipTypes: relationshipTypes.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean),
      minimumConfidence,
      includeExternal,
    };
  }

  function showSubgraph(node: GraphNode) {
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

  function showImpact(mode: "DEPENDENTS" | "DEPENDENCIES") {
    const node = selectedNode ?? root;
    if (!node) return;
    void run(
      () => api.impact({ objectId: node.id, mode, maxDepth: 5, ...graphFilters() }),
      (result) => {
        setGraph(result);
        setRoot(node);
        setAnalysisNote(mode === "DEPENDENTS"
          ? "Becsült hatás: az objektumtól közvetlenül vagy közvetve függő elemek."
          : "Függőségek: az objektum által közvetlenül vagy közvetve használt elemek.");
      },
    );
  }

  function showPath(target: GraphNode, mode: "HOPS" | "WEIGHTED") {
    if (!root || root.id === target.id) return;
    void run(
      () => api.paths({
        sourceId: root.id, targetId: target.id, mode, directed: false, maxPaths: 1,
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
        setAnalysisNote(`${mode === "HOPS" ? "Legrövidebb" : "Legrelevánsabb"} útvonal: ${path.hops} lépés.`);
      },
    );
  }

  return (
    <section className="explorer-panel">
      <div className="scan-heading">
        <span className="scan-number">03</span>
        <div><p className="overline">Gráfböngésző</p><h3>Keresés és interaktív feltárás</h3></div>
        {root && <span className="explorer-root">{root.owner}.{root.name}</span>}
      </div>

      <form className="object-search" onSubmit={submitSearch}>
        <label>
          <span>Objektumnév vagy stabil ID</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="például ORDER*" />
        </label>
        <label>
          <span>Owner</span>
          <input value={owner} onChange={(event) => setOwner(event.target.value)} placeholder="SALES" />
        </label>
        <label>
          <span>Típus</span>
          <input value={objectType} onChange={(event) => setObjectType(event.target.value)} placeholder="TABLE" />
        </label>
        <label>
          <span>Állapot</span>
          <input value={status} onChange={(event) => setStatus(event.target.value)} placeholder="VALID" />
        </label>
        <button className="primary-button" disabled={busy}>Keresés</button>
      </form>

      {error && <div className="error-banner" role="alert"><strong>Gráfhiba</strong><span>{error}</span></div>}

      <div className="explorer-layout">
        <aside className="search-results">
          <div className="result-count">
            <span>Találatok</span><strong>{search?.total ?? 0}</strong>
          </div>
          {!search && <p className="muted-copy">Keress név, owner vagy objektumtípus alapján.</p>}
          {search?.items.map((node) => (
            <article key={node.id} className={root?.id === node.id ? "active" : ""}>
              <span>{node.objectType}</span>
              <strong>{node.owner}.{node.name}</strong>
              <div>
                <button type="button" onClick={() => showSubgraph(node)}>Gráf</button>
                {root && root.id !== node.id && (
                  <>
                    <button type="button" onClick={() => showPath(node, "HOPS")}>Rövid út</button>
                    <button type="button" onClick={() => showPath(node, "WEIGHTED")}>Releváns út</button>
                  </>
                )}
              </div>
            </article>
          ))}
        </aside>

        <div className="graph-workspace">
          <div className="graph-toolbar">
            <label>Mélység
              <select value={depth} onChange={(event) => setDepth(Number(event.target.value))}>
                <option value={1}>1</option><option value={2}>2</option><option value={3}>3</option>
              </select>
            </label>
            <label>Irány
              <select value={direction} onChange={(event) => setDirection(event.target.value as typeof direction)}>
                <option value="BOTH">Mindkettő</option><option value="OUTGOING">Kimenő</option><option value="INCOMING">Bejövő</option>
              </select>
            </label>
            <label>Kapcsolattípusok
              <input aria-label="Kapcsolattípusok" value={relationshipTypes} onChange={(event) => setRelationshipTypes(event.target.value)} placeholder="DEPENDS_ON, FOREIGN_KEY" />
            </label>
            <label>Min. confidence
              <input aria-label="Minimum confidence" type="number" min="0" max="1" step="0.05" value={minimumConfidence} onChange={(event) => setMinimumConfidence(Number(event.target.value))} />
            </label>
            <label className="graph-filter-check"><input type="checkbox" checked={includeExternal} onChange={(event) => setIncludeExternal(event.target.checked)} />Külső objektumok</label>
            <button type="button" onClick={refreshSubgraph} disabled={!root || busy}>Újratöltés</button>
            <button type="button" onClick={() => showImpact("DEPENDENTS")} disabled={!root || busy}>Hatás</button>
            <button type="button" onClick={() => showImpact("DEPENDENCIES")} disabled={!root || busy}>Függőségek</button>
          </div>
          {graph.nodes.length ? (
            <GraphCanvas nodes={graph.nodes} edges={graph.edges} onSelectNode={selectNode} onSelectEdge={selectEdge} />
          ) : (
            <div className="graph-placeholder"><span>⌘</span><p>Nyiss meg egy keresési találatot a részgráf megjelenítéséhez.</p></div>
          )}
          {(graph.truncated || analysisNote) && (
            <div className={graph.truncated ? "graph-notice warning" : "graph-notice"}>
              {graph.truncated ? graph.suggestion ?? "Az eredmény elérte a szerveroldali limitet." : analysisNote}
            </div>
          )}
        </div>

        <aside className="detail-panel">
          <p className="overline">Kijelölt elem</p>
          {selectedNode && (
            <>
              <h4>{selectedNode.owner}.{selectedNode.name}</h4>
              <dl>
                <div><dt>Típus</dt><dd>{selectedNode.objectType}</dd></div>
                <div><dt>Állapot</dt><dd>{selectedNode.status ?? "—"}</dd></div>
                <div><dt>Mélység</dt><dd>{selectedNode.depth ?? 0}</dd></div>
                <div><dt>Külső</dt><dd>{selectedNode.isExternal ? "igen" : "nem"}</dd></div>
              </dl>
              <code>{selectedNode.id}</code>
            </>
          )}
          {selectedEdge && (
            <>
              <h4>{selectedEdge.relationshipType}</h4>
              <dl>
                <div><dt>Confidence</dt><dd>{selectedEdge.confidence.toFixed(2)}</dd></div>
                {selectedEdge.effectiveWeight !== undefined && <div><dt>Effektív súly</dt><dd>{selectedEdge.effectiveWeight.toFixed(3)}</dd></div>}
                {selectedEdge.stepCost !== undefined && <div><dt>Lépésköltség</dt><dd>{selectedEdge.stepCost.toFixed(3)}</dd></div>}
                <div><dt>Forrás</dt><dd>{selectedEdge.origin}</dd></div>
              </dl>
              <h5>Evidence</h5>
              {selectedEdge.evidence.length
                ? selectedEdge.evidence.map((item, index) => <pre key={`${item.sourceView}-${index}`}>{item.sourceView}{"\n"}{JSON.stringify(item.details, null, 2)}</pre>)
                : <p className="muted-copy">Nincs külön evidence rekord.</p>}
            </>
          )}
          {!selectedNode && !selectedEdge && <p className="muted-copy">Kattints egy node-ra vagy élre.</p>}
        </aside>
      </div>
    </section>
  );
}
