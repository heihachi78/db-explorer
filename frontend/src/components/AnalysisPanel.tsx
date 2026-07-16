import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import {
  ApiError,
  api,
  type AnalysisComparison,
  type AnalysisEstimate,
  type AnalysisHierarchy,
  type AnalysisRun,
  type CommunityDetail,
  type CommunityGraph,
  type CommunityMetrics,
  type ExportJob,
  type HierarchyNodeDetail,
  type HierarchyTreeNode,
  type CommunityObjectResult,
  type NamedSubgraph,
  type SubgraphResult,
} from "../api/client";
import { CommunityGraphCanvas } from "./CommunityGraphCanvas";
import { GraphCanvas } from "./GraphCanvas";


const ACTIVE_ANALYSIS_STATES = new Set(["QUEUED", "RUNNING"]);
const DEFAULT_EDGE_WEIGHTS = {
  FOREIGN_KEY: 5,
  TRIGGER_ON: 4,
  DEPENDS_ON: 3,
  POINTS_TO: 1,
  INDEX_ON: 0.5,
};
const EDGE_WEIGHT_LABELS: Record<keyof typeof DEFAULT_EDGE_WEIGHTS, string> = {
  FOREIGN_KEY: "Idegen kulcs",
  TRIGGER_ON: "Trigger",
  DEPENDS_ON: "Függőség",
  POINTS_TO: "Synonym",
  INDEX_ON: "Index",
};

function percent(value: number | undefined) {
  return value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;
}

function formatBytes(value: number) {
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  return `${(value / 1024 ** 3).toFixed(2)} GiB`;
}

function ComparisonChart({ comparison }: { comparison: AnalysisComparison }) {
  const points = comparison.items
    .map((item) => ({
      resolution: Number(item.config.resolution ?? 0),
      communities: item.summary?.communityCount ?? 0,
    }))
    .sort((left, right) => left.resolution - right.resolution);
  const maximum = Math.max(1, ...points.map((item) => item.communities));
  const polyline = points.map((item, index) => {
    const x = 30 + index * (260 / Math.max(1, points.length - 1));
    const y = 105 - item.communities / maximum * 75;
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg className="comparison-chart" viewBox="0 0 320 130" role="img" aria-label="Resolution és közösségszám görbe">
      <line x1="30" y1="105" x2="295" y2="105" /><line x1="30" y1="20" x2="30" y2="105" />
      <polyline points={polyline} />
      {points.map((item, index) => {
        const x = 30 + index * (260 / Math.max(1, points.length - 1));
        const y = 105 - item.communities / maximum * 75;
        return <g key={`${item.resolution}-${index}`}><circle cx={x} cy={y} r="4" /><text x={x} y="121">{item.resolution}</text></g>;
      })}
    </svg>
  );
}

function HierarchyBranch({
  node,
  selectedId,
  onSelect,
}: {
  node: HierarchyTreeNode;
  selectedId?: string;
  onSelect: (hierarchyId: string) => void;
}) {
  const [expanded, setExpanded] = useState(node.level === 0);
  return (
    <li>
      <div className="hierarchy-node-row">
        <button
          type="button"
          className={selectedId === node.hierarchyId ? "selected" : ""}
          onClick={() => onSelect(node.hierarchyId)}
        >
          <strong>{node.metrics.suggestedName}</strong>
          <span>{node.nodeCount} node · szint {node.level} · r={node.resolution.toLocaleString("hu-HU", { maximumFractionDigits: 4 })}</span>
          {node.stopReason && <small>{node.stopReason}</small>}
        </button>
        {node.children.length > 0 && <button
          type="button"
          className="hierarchy-expand"
          aria-label={`${node.metrics.suggestedName} gyermekei ${expanded ? "elrejtése" : "megjelenítése"}`}
          aria-expanded={expanded}
          onClick={() => setExpanded((current) => !current)}
        >{expanded ? "−" : "+"}</button>}
      </div>
      {expanded && node.children.length > 0 && (
        <ul>{node.children.map((child) => (
          <HierarchyBranch key={child.hierarchyId} node={child} selectedId={selectedId} onSelect={onSelect} />
        ))}</ul>
      )}
    </li>
  );
}

export function AnalysisPanel({
  operationActive = false,
  sourceRevision = 0,
  activeSubgraph,
  onSubgraphCreated,
}: {
  operationActive?: boolean;
  sourceRevision?: number;
  activeSubgraph: NamedSubgraph | null;
  onSubgraphCreated: (subgraph: NamedSubgraph) => void;
}) {
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<AnalysisRun | null>(null);
  const [communities, setCommunities] = useState<CommunityMetrics[]>([]);
  const [communityGraph, setCommunityGraph] = useState<CommunityGraph | null>(null);
  const [communityDetail, setCommunityDetail] = useState<CommunityDetail | null>(null);
  const [communityObjects, setCommunityObjects] = useState<CommunityObjectResult | null>(null);
  const [communitySubgraph, setCommunitySubgraph] = useState<SubgraphResult | null>(null);
  const [communityObjectQuery, setCommunityObjectQuery] = useState("");
  const [communityObjectOwner, setCommunityObjectOwner] = useState("");
  const [communityObjectType, setCommunityObjectType] = useState("");
  const [derivedSubgraphName, setDerivedSubgraphName] = useState("");
  const [hierarchy, setHierarchy] = useState<AnalysisHierarchy | null>(null);
  const [hierarchyDetail, setHierarchyDetail] = useState<HierarchyNodeDetail | null>(null);
  const [annotationName, setAnnotationName] = useState("");
  const [annotationNote, setAnnotationNote] = useState("");
  const [comparisonIds, setComparisonIds] = useState<string[]>([]);
  const [comparison, setComparison] = useState<AnalysisComparison | null>(null);
  const [exportJob, setExportJob] = useState<ExportJob | null>(null);
  const [name, setName] = useState("Leiden – normalizált hubok");
  const [objective, setObjective] = useState<"CPM" | "MODULARITY">("MODULARITY");
  const [resolution, setResolution] = useState(1.0);
  const [seed, setSeed] = useState(42);
  const [minimumConfidence, setMinimumConfidence] = useState(0.8);
  const [hubPolicy, setHubPolicy] = useState<"NONE" | "DEGREE_NORMALIZATION" | "EXCLUDE_TOP_HUBS">("DEGREE_NORMALIZATION");
  const [includeTechnicalObjects, setIncludeTechnicalObjects] = useState(false);
  const [edgeWeights, setEdgeWeights] = useState({ ...DEFAULT_EDGE_WEIGHTS });
  const [hierarchyBaseResolution, setHierarchyBaseResolution] = useState(0.2);
  const [hierarchyChildResolution, setHierarchyChildResolution] = useState(1.0);
  const [hierarchyMinimumSize, setHierarchyMinimumSize] = useState(20);
  const [hierarchyMaxDepth, setHierarchyMaxDepth] = useState(3);
  const [hierarchyMaxCommunities, setHierarchyMaxCommunities] = useState(10_000);
  const [hierarchyOverrides, setHierarchyOverrides] = useState("");
  const [estimate, setEstimate] = useState<AnalysisEstimate | null>(null);
  const [estimatePending, setEstimatePending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedAnalysisIdRef = useRef<string | null>(null);

  async function refresh() {
    try {
      const nextRuns = await api.analyses();
      setRuns(nextRuns);
      setSelectedRun((current) => current
        ? nextRuns.find((run) => run.id === current.id) ?? current
        : current);
    } catch {
      // The global configuration panel reports server availability.
    }
  }

  const analysisPollingActive = runs.some((run) => ACTIVE_ANALYSIS_STATES.has(run.status));
  const visibleRuns = useMemo(() => activeSubgraph
    ? runs.filter((run) => run.config.subgraphId === activeSubgraph.id)
    : [], [activeSubgraph, runs]);

  useEffect(() => {
    if (sourceRevision > 0) {
      loadedAnalysisIdRef.current = null;
      setSelectedRun(null); setCommunities([]); setCommunityGraph(null); setCommunityDetail(null);
      setCommunityObjects(null); setCommunitySubgraph(null);
      setHierarchy(null); setHierarchyDetail(null); setComparison(null); setComparisonIds([]);
    }
    void refresh();
  }, [sourceRevision]);

  useEffect(() => {
    loadedAnalysisIdRef.current = null;
    setSelectedRun(null); setCommunities([]); setCommunityGraph(null); setCommunityDetail(null);
    setCommunityObjects(null); setCommunitySubgraph(null); setHierarchy(null); setHierarchyDetail(null);
    setComparison(null); setComparisonIds([]); setExportJob(null); setError(null);
  }, [activeSubgraph?.id]);

  useEffect(() => {
    if (!analysisPollingActive) return;
    let disposed = false;
    async function poll() { if (!disposed) await refresh(); }
    const timer = setInterval(() => { void poll(); }, 2000);
    return () => { disposed = true; clearInterval(timer); };
  }, [analysisPollingActive]);

  function analysisPayload() {
    return {
      name, objective, resolution, seed, minimumConfidence, hubPolicy,
      includeTechnicalObjects, edgeWeights, subgraphId: activeSubgraph?.id,
    };
  }

  useEffect(() => {
    if (!activeSubgraph) {
      setEstimate(null); setEstimatePending(false); return;
    }
    let disposed = false;
    setEstimatePending(true);
    const timer = setTimeout(() => {
      void api.estimateAnalysis(analysisPayload()).then((result) => {
        if (!disposed && typeof result.withinLimits === "boolean") setEstimate(result);
      }).catch(() => {
        if (!disposed) setEstimate(null);
      }).finally(() => {
        if (!disposed) setEstimatePending(false);
      });
    }, 400);
    return () => { disposed = true; clearTimeout(timer); };
  }, [name, objective, resolution, seed, minimumConfidence, hubPolicy, includeTechnicalObjects, edgeWeights, activeSubgraph?.id]);

  async function start(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      const result = await api.startAnalysis(analysisPayload());
      await refresh();
      setSelectedRun({
        id: result.analysisId, name, status: "QUEUED", algorithm: "LEIDEN",
        config: {}, summary: null, errorMessage: null,
        createdAt: new Date().toISOString(), startedAt: null, finishedAt: null,
      });
      setCommunities([]); setCommunityGraph(null); setCommunityDetail(null);
      setCommunityObjects(null); setCommunitySubgraph(null);
      setHierarchy(null); setHierarchyDetail(null);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Az elemzés nem indítható el.");
    } finally { setBusy(false); }
  }

  async function startProfile(kind: "resolution" | "seed") {
    setBusy(true); setError(null); setComparison(null);
    try {
      const result = kind === "resolution"
        ? await api.startResolutionProfile(analysisPayload())
        : await api.startSeedProfile(analysisPayload());
      setComparisonIds(result.analysisIds);
      setSelectedRun(null); setCommunities([]); setCommunityGraph(null); setCommunityDetail(null);
      setCommunityObjects(null); setCommunitySubgraph(null);
      setHierarchy(null); setHierarchyDetail(null);
      await refresh();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A profil nem indítható el.");
    } finally { setBusy(false); }
  }

  function parsedHierarchyOverrides() {
    const result: Record<string, number> = {};
    for (const item of hierarchyOverrides.split(",").map((value) => value.trim()).filter(Boolean)) {
      const [hierarchyId, rawResolution, ...extra] = item.split("=").map((value) => value.trim());
      const resolutionValue = Number(rawResolution);
      if (extra.length || !hierarchyId || !rawResolution || !Number.isFinite(resolutionValue) || resolutionValue <= 0) {
        throw new Error("A felülírás formátuma például: 0=1.5, 0.2=2.0");
      }
      result[hierarchyId] = resolutionValue;
    }
    return result;
  }

  async function startHierarchy() {
    setBusy(true); setError(null); setComparison(null);
    try {
      const result = await api.startHierarchy({
        ...analysisPayload(),
        resolution: hierarchyBaseResolution,
        hierarchyChildResolution,
        hierarchyMinimumSize,
        hierarchyMaxDepth,
        hierarchyMaxCommunities,
        hierarchyResolutionOverrides: parsedHierarchyOverrides(),
      });
      await refresh();
      setSelectedRun({
        id: result.analysisId, name, status: "QUEUED", algorithm: "LEIDEN",
        config: { hierarchyEnabled: true }, summary: null, errorMessage: null,
        createdAt: new Date().toISOString(), startedAt: null, finishedAt: null,
      });
      setCommunities([]); setCommunityGraph(null); setCommunityDetail(null);
      setCommunityObjects(null); setCommunitySubgraph(null);
      setHierarchy(null); setHierarchyDetail(null);
    } catch (reason) {
      setError(reason instanceof ApiError || reason instanceof Error
        ? reason.message : "A hierarchikus elemzés nem indítható el.");
    } finally { setBusy(false); }
  }

  async function inspect(run: AnalysisRun) {
    setSelectedRun(run); setCommunityDetail(null); setHierarchyDetail(null); setExportJob(null); setError(null);
    if (run.status !== "SUCCEEDED") {
      loadedAnalysisIdRef.current = null;
      setCommunities([]); setCommunityGraph(null); setHierarchy(null); return;
    }
    loadedAnalysisIdRef.current = run.id;
    setBusy(true);
    try {
      const [nextCommunities, nextGraph, nextHierarchy] = await Promise.all([
        api.communities(run.id), api.communityGraph(run.id),
        run.config.hierarchyEnabled ? api.hierarchy(run.id) : Promise.resolve(null),
      ]);
      setCommunities(nextCommunities); setCommunityGraph(nextGraph); setHierarchy(nextHierarchy);
    } catch (reason) {
      if (loadedAnalysisIdRef.current === run.id) loadedAnalysisIdRef.current = null;
      setError(reason instanceof ApiError ? reason.message : "A közösségek nem tölthetők be.");
    } finally { setBusy(false); }
  }

  useEffect(() => {
    if (selectedRun?.status === "SUCCEEDED" && loadedAnalysisIdRef.current !== selectedRun.id) {
      void inspect(selectedRun);
    }
  }, [selectedRun?.id, selectedRun?.status]);

  const selectedRunId = selectedRun?.id;

  const selectCommunity = useCallback(async (communityId: number) => {
    if (!selectedRunId) return;
    setBusy(true); setError(null);
    try {
      const [detail, objects, graph] = await Promise.all([
        api.community(selectedRunId, communityId),
        api.communityObjects(selectedRunId, communityId, { pageSize: 100 }),
        api.communitySubgraph(selectedRunId, communityId),
      ]);
      setCommunityDetail(detail);
      setCommunityObjects(objects); setCommunitySubgraph(graph);
      setCommunityObjectQuery(""); setCommunityObjectOwner(""); setCommunityObjectType("");
      setAnnotationName(detail.annotation?.name ?? detail.metrics.suggestedName);
      setAnnotationNote(detail.annotation?.note ?? "");
      setDerivedSubgraphName(detail.annotation?.name ?? detail.metrics.suggestedName);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A közösség nem tölthető be.");
    } finally { setBusy(false); }
  }, [selectedRunId]);

  async function searchCommunityObjects() {
    if (!selectedRun || !communityDetail) return;
    setBusy(true); setError(null);
    try {
      setCommunityObjects(await api.communityObjects(
        selectedRun.id,
        communityDetail.metrics.communityId,
        {
          q: communityObjectQuery,
          owner: communityObjectOwner,
          objectType: communityObjectType,
          pageSize: 100,
        },
      ));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A közösség objektumai nem kereshetők.");
    } finally { setBusy(false); }
  }

  async function saveCommunityAsSubgraph() {
    if (!selectedRun || !communityDetail || !activeSubgraph || !derivedSubgraphName.trim()) return;
    setBusy(true); setError(null);
    try {
      const created = await api.createSubgraphFromCommunity({
        name: derivedSubgraphName.trim(),
        analysisId: selectedRun.id,
        communityId: communityDetail.metrics.communityId,
        parentId: activeSubgraph.id,
      });
      onSubgraphCreated(created);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A közösség nem menthető részgráfként.");
    } finally { setBusy(false); }
  }

  const selectHierarchyNode = useCallback(async (hierarchyId: string) => {
    if (!selectedRun) return;
    setBusy(true); setError(null);
    try {
      setHierarchyDetail(await api.hierarchyNode(selectedRun.id, hierarchyId));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A hierarchikus közösség nem tölthető be.");
    } finally { setBusy(false); }
  }, [selectedRun]);

  async function saveAnnotation() {
    if (!selectedRun || !communityDetail) return;
    setBusy(true); setError(null);
    try {
      await api.saveAnnotation({
        analysisId: selectedRun.id, communityId: communityDetail.metrics.communityId,
        name: annotationName || null, note: annotationNote || null,
      });
      await inspect(selectedRun);
      await selectCommunity(communityDetail.metrics.communityId);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A megjegyzés nem menthető.");
    } finally { setBusy(false); }
  }

  function toggleComparison(runId: string) {
    setComparisonIds((current) => current.includes(runId)
      ? current.filter((id) => id !== runId)
      : current.length < 10 ? [...current, runId] : current);
    setComparison(null);
  }

  async function compareSelected() {
    setBusy(true); setError(null);
    try { setComparison(await api.compareAnalyses(comparisonIds)); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "A futások nem hasonlíthatók össze."); }
    finally { setBusy(false); }
  }

  async function exportResult(format: ExportJob["format"]) {
    if (!selectedRun) return;
    setBusy(true); setError(null); setExportJob(null);
    try {
      const started = await api.startExport(selectedRun.id, format);
      for (let attempt = 0; attempt < 100; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 100));
        const job = await api.exportStatus(started.exportId);
        setExportJob(job);
        if (!["QUEUED", "RUNNING"].includes(job.status)) break;
      }
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Az export nem készíthető el.");
    } finally { setBusy(false); }
  }

  async function cancel(run: AnalysisRun) {
    try { await api.cancelAnalysis(run.id); await refresh(); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Az elemzés nem szakítható meg."); }
  }

  async function remove(run: AnalysisRun) {
    try {
      await api.deleteAnalysis(run.id);
      if (selectedRun?.id === run.id) {
        setSelectedRun(null); setCommunities([]); setCommunityGraph(null);
        setHierarchy(null); setHierarchyDetail(null);
      }
      setComparisonIds((current) => current.filter((id) => id !== run.id));
      await refresh();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Az elemzés nem törölhető."); }
  }

  const anyActive = analysisPollingActive;

  return (
    <section className="analysis-panel">
      <div className="scan-heading">
        <span className="scan-number">04</span>
        <div><p className="overline">Közösségelemzés</p><h3>Leiden futások és elemzői nézetek</h3></div>
        <span className="analysis-run-count">{activeSubgraph ? `${activeSubgraph.name} · ${activeSubgraph.nodeCount} node` : "Előbb válassz részgráfot"}</span>
      </div>
      {error && <div className="error-banner" role="alert"><strong>Elemzési hiba</strong><span>{error}</span></div>}

      <div className="analysis-layout">
        <form className="analysis-form" onSubmit={start} noValidate>
          <h4>Új futás</h4>
          {!activeSubgraph && <p className="analysis-warning">A közösségelemzés csak egy elnevezett, aktív részgráfon indítható.</p>}
          <label>Név<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
          <div className="analysis-form-row">
            <label>Objective<select value={objective} onChange={(event) => setObjective(event.target.value as typeof objective)}><option>CPM</option><option>MODULARITY</option></select></label>
            <label>Resolution<input type="number" min="0.01" max="100" step="0.01" value={resolution} onChange={(event) => setResolution(Number(event.target.value))} /></label>
          </div>
          <div className="analysis-form-row">
            <label>Seed<input type="number" value={seed} onChange={(event) => setSeed(Number(event.target.value))} /></label>
            <label>Min. confidence<input type="number" min="0" max="1" step="0.05" value={minimumConfidence} onChange={(event) => setMinimumConfidence(Number(event.target.value))} /></label>
          </div>
          <label>Hub policy<select value={hubPolicy} onChange={(event) => setHubPolicy(event.target.value as typeof hubPolicy)}><option value="DEGREE_NORMALIZATION">Fokszám-normalizálás</option><option value="NONE">Nincs korrekció</option><option value="EXCLUDE_TOP_HUBS">Top 1% kizárása</option></select></label>
          <label className="checkbox-label"><input type="checkbox" checked={includeTechnicalObjects} onChange={(event) => setIncludeTechnicalObjects(event.target.checked)} />Technikai objektumok bevonása</label>
          {includeTechnicalObjects && <p className="analysis-warning">Az indexek és synonymok torzíthatják a közösséghatárokat.</p>}
          <details className="hierarchy-config">
            <summary>Kapcsolattípus-súlyok</summary>
            <div className="analysis-form-row">
              {(Object.keys(DEFAULT_EDGE_WEIGHTS) as Array<keyof typeof DEFAULT_EDGE_WEIGHTS>).map((relationshipType) => (
                <label key={relationshipType}>{EDGE_WEIGHT_LABELS[relationshipType]}
                  <input
                    aria-label={`${EDGE_WEIGHT_LABELS[relationshipType]} súlya`}
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={edgeWeights[relationshipType]}
                    onChange={(event) => setEdgeWeights((current) => ({
                      ...current,
                      [relationshipType]: Number(event.target.value),
                    }))}
                  />
                </label>
              ))}
            </div>
          </details>
          <div className={`analysis-estimate ${estimate && !estimate.withinLimits ? "blocked" : ""}`} aria-live="polite">
            <strong>{estimatePending ? "Méretbecslés…" : "Futtatás előtti becslés"}</strong>
            {estimate && <>
              <span>{estimate.estimatedNodeCount.toLocaleString("hu-HU")} node · {estimate.estimatedRelationshipCount.toLocaleString("hu-HU")} kapcsolat</span>
              <span>{formatBytes(estimate.estimatedMemoryBytes)} · {estimate.sizeCategory}</span>
              {estimate.approximate && <small>Közelítő becslés a jelenlegi szűrőkkel.</small>}
              {estimate.warnings.map((warning) => <small key={warning}>{warning}</small>)}
            </>}
          </div>
          <details className="hierarchy-config">
            <summary>Kísérleti hierarchia beállításai</summary>
            <p>Az alacsony alap-resolution nagy csoportokat keres, majd csak a méretküszöb feletti közösségeket bontja tovább.</p>
            <div className="analysis-form-row">
              <label>Alap resolution<input aria-label="Hierarchia alap resolution" type="number" min="0.01" max="100" step="0.01" value={hierarchyBaseResolution} onChange={(event) => setHierarchyBaseResolution(Number(event.target.value))} /></label>
              <label>Gyermek resolution<input aria-label="Hierarchia gyermek resolution" type="number" min="0.01" max="100" step="0.01" value={hierarchyChildResolution} onChange={(event) => setHierarchyChildResolution(Number(event.target.value))} /></label>
            </div>
            <div className="analysis-form-row">
              <label>Minimum méret<input aria-label="Hierarchia minimum méret" type="number" min="2" max="100000" value={hierarchyMinimumSize} onChange={(event) => setHierarchyMinimumSize(Number(event.target.value))} /></label>
              <label>Max. mélység<input aria-label="Hierarchia maximum mélység" type="number" min="1" max="5" value={hierarchyMaxDepth} onChange={(event) => setHierarchyMaxDepth(Number(event.target.value))} /></label>
            </div>
            <label>Maximum közösség<input aria-label="Hierarchia maximum közösség" type="number" min="2" max="100000" value={hierarchyMaxCommunities} onChange={(event) => setHierarchyMaxCommunities(Number(event.target.value))} /></label>
            <label>Szülőnkénti felülírás<input aria-label="Hierarchia resolution felülírások" value={hierarchyOverrides} onChange={(event) => setHierarchyOverrides(event.target.value)} placeholder="0=1.5, 0.2=2.0" /></label>
            <button className="secondary-button analysis-profile-button" type="button" onClick={() => void startHierarchy()} disabled={!activeSubgraph || busy || anyActive || operationActive || estimate?.withinLimits === false}>Kísérleti hierarchia indítása</button>
          </details>
          <p className="parameter-hint">Az alapsúlyokat confidence és a választott hub policy korrigálja. Az alapértelmezett profil a logikai objektumokra optimalizált.</p>
          <button className="primary-button" type="submit" disabled={!activeSubgraph || busy || anyActive || operationActive || estimate?.withinLimits === false}>Elemzés indítása</button>
          <button className="secondary-button analysis-profile-button" type="button" onClick={() => void startProfile("resolution")} disabled={!activeSubgraph || busy || anyActive || operationActive || estimate?.withinLimits === false}>6 pontos resolution profil</button>
          <button className="secondary-button analysis-profile-button" type="button" onClick={() => void startProfile("seed")} disabled={!activeSubgraph || busy || anyActive || operationActive || estimate?.withinLimits === false}>5 seed stabilitásprofil</button>
        </form>

        <div className="analysis-runs">
          <h4>Futások</h4>
          {visibleRuns.length === 0 && <p className="muted-copy">Ehhez a részgráfhoz még nincs elemzési futás.</p>}
          {visibleRuns.map((run) => (
            <article key={run.id} className={selectedRun?.id === run.id ? "selected" : ""}>
              <label className="compare-check" title="Kijelölés összehasonlításhoz"><input aria-label={`${run.name} összehasonlítása`} type="checkbox" checked={comparisonIds.includes(run.id)} disabled={run.status !== "SUCCEEDED"} onChange={() => toggleComparison(run.id)} /><span>⇄</span></label>
              <button className="run-main" type="button" onClick={() => void inspect(run)}>
                <span>{run.status}</span><strong>{run.name}</strong>
                <small>{run.summary ? `${run.summary.communityCount} közösség · ${run.summary.runtimeSeconds.toFixed(3)} s` : "Eredményre vár"}</small>
              </button>
              <div className="run-actions">
                {ACTIVE_ANALYSIS_STATES.has(run.status)
                  ? <button type="button" onClick={() => void cancel(run)}>Megszakítás</button>
                  : <button type="button" onClick={() => void remove(run)}>Törlés</button>}
              </div>
              <details className="run-config"><summary>Paraméterek</summary><dl>
                <div><dt>Részgráf</dt><dd>{String(run.config.subgraphId ?? "teljes forrásgráf")}</dd></div>
                <div><dt>Objective</dt><dd>{String(run.config.objective ?? "—")}</dd></div>
                <div><dt>Resolution</dt><dd>{String(run.config.resolution ?? "—")}</dd></div>
                <div><dt>Seed</dt><dd>{String(run.config.seed ?? "—")}</dd></div>
                <div><dt>Min. confidence</dt><dd>{String(run.config.minimumConfidence ?? "—")}</dd></div>
                <div><dt>Hub policy</dt><dd>{String(run.config.hubPolicy ?? "—")}</dd></div>
                <div><dt>Technikai objektumok</dt><dd>{run.config.includeTechnicalObjects ? "igen" : "nem"}</dd></div>
              </dl><pre>{JSON.stringify(run.config.edgeWeights ?? {}, null, 2)}</pre></details>
            </article>
          ))}
          <button className="compare-button" type="button" disabled={comparisonIds.length < 2 || busy || anyActive} onClick={() => void compareSelected()}>Kijelöltek összehasonlítása ({comparisonIds.length})</button>
        </div>

        <div className="analysis-results">
          <h4>Eredmény</h4>
          {!selectedRun && <p className="muted-copy">Válassz egy sikeres futást a részletekhez.</p>}
          {selectedRun?.errorMessage && <p className="analysis-warning">{selectedRun.errorMessage}</p>}
          {selectedRun?.summary && (
            <>
              <div className="analysis-metrics">
                <div><span>Közösség</span><strong>{selectedRun.summary.communityCount}</strong></div>
                <div><span>Belső súly</span><strong>{percent(selectedRun.summary.internalWeightRatio)}</strong></div>
                <div><span>Sématisztaság</span><strong>{percent(selectedRun.summary.schemaPurity)}</strong></div>
                <div><span>Medián conductance</span><strong>{selectedRun.summary.medianConductance.toFixed(3)}</strong></div>
              </div>
              {communityGraph && <div className="analysis-result-map">
                <p>Minden kör egy közösség, a vonalak a közösségek közötti összesített objektumkapcsolatok.</p>
                <CommunityGraphCanvas graph={communityGraph} />
              </div>}
              <div className="export-actions">
                <span>Export</span>{(["JSON", "CSV", "SVG", "PNG"] as const).map((format) => <button type="button" key={format} disabled={busy || operationActive} onClick={() => void exportResult(format)}>{format}</button>)}
                {exportJob?.status === "SUCCEEDED" && exportJob.downloadUrl && <a href={exportJob.downloadUrl}>{exportJob.filename ?? "Export letöltése"}</a>}
                {exportJob?.status === "FAILED" && <em>{exportJob.errorMessage}</em>}
              </div>
            </>
          )}
        </div>
      </div>

      {comparison && (
        <section className="analysis-insight comparison-view">
          <div><p className="overline">Futás-összehasonlítás</p><h4>Paraméterek, minőség és particionálási egyezés</h4></div>
          <div className="comparison-layout">
            <ComparisonChart comparison={comparison} />
            <div className="comparison-table">
              <div><b>Futás</b><b>r</b><b>Közösség</b><b>Quality</b><b>Conductance</b><b>Sématisztaság</b></div>
              {comparison.items.map((item) => <div key={item.id}><span>{item.name}</span><span>{String(item.config.resolution)}</span><span>{item.summary?.communityCount}</span><span>{item.summary?.quality.toFixed(3)}</span><span>{item.summary?.medianConductance.toFixed(3)}</span><span>{percent(item.summary?.schemaPurity)}</span></div>)}
            </div>
          </div>
          <div className="agreement-list">
            {comparison.agreement.pairwise.map((item) => <div key={`${item.leftAnalysisId}-${item.rightAnalysisId}`}><span>ARI <strong>{item.adjustedRandIndex.toFixed(3)}</strong></span><span>NMI <strong>{item.normalizedMutualInformation.toFixed(3)}</strong></span><span>VI <strong>{item.variationOfInformation.toFixed(3)}</strong></span></div>)}
          </div>
        </section>
      )}

      {selectedRun?.summary && hierarchy && (
        <section className="analysis-insight hierarchy-workbench">
          <div className="insight-heading">
            <div><p className="overline">Kísérleti hierarchia</p><h4>Hierarchikus közösségtérkép</h4></div>
            <span>{hierarchy.summary.hierarchyNodeCount} csoport · {hierarchy.summary.leafCount} levél · {hierarchy.summary.maximumDepthReached} szint</span>
          </div>
          <p className="analysis-warning">{hierarchy.summary.warning}</p>
          {hierarchy.summary.truncated && <p className="analysis-warning">A hierarchia elérte a konfigurált {hierarchy.summary.maximumCommunities} közösséges limitet; egyes ágak levélként maradtak.</p>}
          <div className="hierarchy-layout">
            <ul className="hierarchy-tree">
              {hierarchy.roots.length === 0 && (
                <li className="muted-copy">Nincs felosztható közösség; a futás csak izolált vagy kizárt objektumokat talált.</li>
              )}
              {hierarchy.roots.map((root) => (
                <HierarchyBranch
                  key={root.hierarchyId}
                  node={root}
                  selectedId={hierarchyDetail?.hierarchyId}
                  onSelect={(hierarchyId) => void selectHierarchyNode(hierarchyId)}
                />
              ))}
            </ul>
            <div className="hierarchy-detail">
              {hierarchyDetail ? <>
                <p className="overline">{hierarchyDetail.hierarchyId} útvonal</p>
                <h4>{hierarchyDetail.metrics.suggestedName}</h4>
                <p>{hierarchyDetail.metrics.nameExplanation}</p>
                <dl>
                  <div><dt>Node-ok</dt><dd>{hierarchyDetail.nodeCount}</dd></div>
                  <div><dt>Resolution</dt><dd>{hierarchyDetail.resolution}</dd></div>
                  <div><dt>Density</dt><dd>{hierarchyDetail.metrics.internalDensity.toFixed(3)}</dd></div>
                  <div><dt>Conductance</dt><dd>{hierarchyDetail.metrics.conductance.toFixed(3)}</dd></div>
                </dl>
                <div className="hierarchy-objects">
                  {hierarchyDetail.objects.slice(0, 50).map((object) => <code key={object.id}>{object.owner}.{object.name} · {object.objectType}</code>)}
                  {hierarchyDetail.objects.length > 50 && <small>…és további {hierarchyDetail.objects.length - 50} objektum</small>}
                </div>
              </> : <p className="muted-copy">Válassz egy faelemet a közösség objektumainak és helyi mutatóinak megtekintéséhez.</p>}
            </div>
          </div>
        </section>
      )}

      {selectedRun?.summary && communityGraph && (
        <section className="analysis-insight community-workbench">
          <div className="insight-heading"><div><p className="overline">Közösségek</p><h4>Részletes közösséglista</h4></div><span>Kattints egy közösség sorára a tagság, a sémabontás, a kapcsolatok és a belső gráf megtekintéséhez.</span></div>
          <div className="community-table community-table--workbench" role="table" aria-label="Közösségek">
            <div className="community-table-head" role="row"><span>ID</span><span>Node</span><span>Név / séma</span><span>Density</span><span>Conductance</span></div>
            {communities.map((community) => (
              <button
                type="button"
                role="row"
                className={communityDetail?.metrics.communityId === community.communityId ? "selected" : ""}
                key={community.communityId}
                onClick={() => void selectCommunity(community.communityId)}
              >
                <span>#{community.communityId}</span><strong>{community.nodeCount}</strong>
                <span>{community.annotation?.name ?? community.suggestedName}<small>{community.dominantSchema} · {percent(community.dominantSchemaRatio)} · {community.stability}</small></span>
                <span>{community.internalDensity.toFixed(3)}</span><span>{community.conductance.toFixed(3)}</span>
              </button>
            ))}
          </div>
          {!communityDetail && <p className="community-selection-hint">Válassz egy sort a közösség részletes vizsgálatához.</p>}
          {communityDetail && (
            <div className="community-detail-card">
              <div>
                <p className="overline">Miért került ide?</p><h4>{communityDetail.annotation?.name ?? communityDetail.metrics.suggestedName}</h4>
                <p>{communityDetail.metrics.nameExplanation}</p>
                <dl><div><dt>Objektumok</dt><dd>{communityDetail.metrics.nodeCount}</dd></div><div><dt>Belső/külső élek</dt><dd>{communityDetail.metrics.internalEdgeCount} / {communityDetail.metrics.externalEdgeCount}</dd></div><div><dt>Belső/külső súly</dt><dd>{communityDetail.metrics.internalWeight.toFixed(2)} / {communityDetail.metrics.externalWeight.toFixed(2)}</dd></div><div><dt>Stabilitás</dt><dd>{communityDetail.metrics.stability}{communityDetail.metrics.stabilityScore !== undefined ? ` · ${percent(communityDetail.metrics.stabilityScore)}` : ""}</dd></div></dl>
                <h5>Séma szerinti bontás</h5>
                <div className="community-schema-breakdown" aria-label="Séma szerinti bontás">
                  {Object.entries(communityDetail.metrics.schemaDistribution)
                    .sort((left, right) => right[1] - left[1])
                    .map(([schema, count]) => <div key={schema}><code>{schema}</code><span><strong>{count}</strong> objektum · {percent(count / communityDetail.metrics.nodeCount)}</span></div>)}
                </div>
              </div>
              <div><h5>Top belső hubok</h5>{communityDetail.metrics.topInternalHubs.slice(0, 5).map((item) => <code key={item.objectId}>{item.objectId} · {item.strength.toFixed(2)}</code>)}<h5>Top bridge objektumok</h5>{communityDetail.metrics.topBridgeObjects.slice(0, 5).map((item) => <code key={item.objectId}>{item.objectId} · {item.externalStrength.toFixed(2)}</code>)}</div>
              <form onSubmit={(event) => { event.preventDefault(); void saveAnnotation(); }}><h5>Elemzői címke</h5><label>Név<input value={annotationName} onChange={(event) => setAnnotationName(event.target.value)} /></label><label>Megjegyzés<textarea rows={4} value={annotationNote} onChange={(event) => setAnnotationNote(event.target.value)} /></label><button className="primary-button" disabled={busy}>Mentés</button></form>
              <div className="community-to-subgraph"><h5>További bontás</h5><p>Mentsd el ezt a közösséget új részgráfként, majd futtass rajta új elemzést.</p><input aria-label="Közösségből létrehozott részgráf neve" value={derivedSubgraphName} onChange={(event) => setDerivedSubgraphName(event.target.value)} /><button type="button" className="primary-button" disabled={busy || !derivedSubgraphName.trim()} onClick={() => void saveCommunityAsSubgraph()}>Mentés és aktiválás részgráfként</button></div>
            </div>
          )}
          {communityDetail && (
            <div className="community-inspection">
              <section className="community-object-search">
                <div><h4>Közösség objektumai</h4><span>{communityObjects?.total ?? 0} találat / {communityDetail.metrics.nodeCount} közösségi tag</span></div>
                <form onSubmit={(event) => { event.preventDefault(); void searchCommunityObjects(); }}>
                  <input aria-label="Keresés a közösségben" value={communityObjectQuery} onChange={(event) => setCommunityObjectQuery(event.target.value)} placeholder="objektumnév vagy stabil ID" />
                  <input aria-label="Közösségi séma" value={communityObjectOwner} onChange={(event) => setCommunityObjectOwner(event.target.value)} placeholder="séma" />
                  <input aria-label="Közösségi objektumtípus" value={communityObjectType} onChange={(event) => setCommunityObjectType(event.target.value)} placeholder="típus" />
                  <button type="submit">Keresés</button>
                </form>
                <div className="community-object-table" role="table">
                  <div role="row"><b>Séma</b><b>Objektum</b><b>Típus</b><b>Státusz</b><b>PageRank</b><b>Belső / külső strength</b></div>
                  {communityObjects?.items.map((object) => <div role="row" key={object.id}><span>{object.owner}</span><code>{object.name}</code><span>{object.objectType}</span><span>{object.status ?? "—"}</span><span>{(object.centrality.PAGERANK ?? 0).toFixed(4)}</span><span>{(object.centrality.INTERNAL_STRENGTH ?? 0).toFixed(2)} / {(object.centrality.EXTERNAL_STRENGTH ?? 0).toFixed(2)}</span></div>)}
                </div>
              </section>
              <section className="community-induced-graph">
                <h4>A közösség belső gráfja</h4>
                {communitySubgraph?.nodes.length ? <GraphCanvas nodes={communitySubgraph.nodes} edges={communitySubgraph.edges} onSelectNode={() => undefined} onSelectEdge={() => undefined} /> : <p className="muted-copy">A közösségnek nincs megjeleníthető belső éle.</p>}
                {communitySubgraph?.truncated && <p className="analysis-warning">{communitySubgraph.suggestion}</p>}
              </section>
            </div>
          )}
        </section>
      )}
    </section>
  );
}
