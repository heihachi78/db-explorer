import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import {
  ApiError,
  api,
  type AnalysisComparison,
  type AnalysisRun,
  type CommunityDetail,
  type CommunityGraph,
  type CommunityMetrics,
  type ExportJob,
} from "../api/client";
import { CommunityGraphCanvas } from "./CommunityGraphCanvas";


const ACTIVE_ANALYSIS_STATES = new Set(["QUEUED", "RUNNING"]);

function percent(value: number | undefined) {
  return value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;
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

export function AnalysisPanel({ operationActive = false }: { operationActive?: boolean }) {
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<AnalysisRun | null>(null);
  const [communities, setCommunities] = useState<CommunityMetrics[]>([]);
  const [communityGraph, setCommunityGraph] = useState<CommunityGraph | null>(null);
  const [communityDetail, setCommunityDetail] = useState<CommunityDetail | null>(null);
  const [annotationName, setAnnotationName] = useState("");
  const [annotationNote, setAnnotationNote] = useState("");
  const [comparisonIds, setComparisonIds] = useState<string[]>([]);
  const [comparison, setComparison] = useState<AnalysisComparison | null>(null);
  const [exportJob, setExportJob] = useState<ExportJob | null>(null);
  const [name, setName] = useState("Leiden – normalizált hubok");
  const [objective, setObjective] = useState<"CPM" | "MODULARITY">("CPM");
  const [resolution, setResolution] = useState(1.0);
  const [seed, setSeed] = useState(42);
  const [minimumConfidence, setMinimumConfidence] = useState(0.8);
  const [hubPolicy, setHubPolicy] = useState<"NONE" | "DEGREE_NORMALIZATION" | "EXCLUDE_TOP_HUBS">("DEGREE_NORMALIZATION");
  const [includeTechnicalObjects, setIncludeTechnicalObjects] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  useEffect(() => {
    let disposed = false;
    async function poll() { if (!disposed) await refresh(); }
    void poll();
    const timer = setInterval(poll, 2000);
    return () => { disposed = true; clearInterval(timer); };
  }, []);

  function analysisPayload() {
    return { name, objective, resolution, seed, minimumConfidence, hubPolicy, includeTechnicalObjects };
  }

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
      await refresh();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A profil nem indítható el.");
    } finally { setBusy(false); }
  }

  async function inspect(run: AnalysisRun) {
    setSelectedRun(run); setCommunityDetail(null); setExportJob(null); setError(null);
    if (run.status !== "SUCCEEDED") { setCommunities([]); setCommunityGraph(null); return; }
    setBusy(true);
    try {
      const [nextCommunities, nextGraph] = await Promise.all([
        api.communities(run.id), api.communityGraph(run.id),
      ]);
      setCommunities(nextCommunities); setCommunityGraph(nextGraph);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A közösségek nem tölthetők be.");
    } finally { setBusy(false); }
  }

  const selectCommunity = useCallback(async (communityId: number) => {
    if (!selectedRun) return;
    setBusy(true); setError(null);
    try {
      const detail = await api.community(selectedRun.id, communityId);
      setCommunityDetail(detail);
      setAnnotationName(detail.annotation?.name ?? detail.metrics.suggestedName);
      setAnnotationNote(detail.annotation?.note ?? "");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A közösség nem tölthető be.");
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
      if (selectedRun?.id === run.id) { setSelectedRun(null); setCommunities([]); setCommunityGraph(null); }
      setComparisonIds((current) => current.filter((id) => id !== run.id));
      await refresh();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Az elemzés nem törölhető."); }
  }

  const anyActive = runs.some((run) => ACTIVE_ANALYSIS_STATES.has(run.status));
  const schemas = useMemo(() => Array.from(new Set(
    communities.flatMap((community) => Object.keys(community.schemaDistribution)),
  )).sort(), [communities]);
  const conductanceRanking = [...communities].sort((left, right) => left.conductance - right.conductance);

  return (
    <section className="analysis-panel">
      <div className="scan-heading">
        <span className="scan-number">04</span>
        <div><p className="overline">Közösségelemzés</p><h3>Leiden futások és elemzői nézetek</h3></div>
        <span className="analysis-run-count">{runs.length} mentett futás</span>
      </div>

      <div className="analysis-layout">
        <form className="analysis-form" onSubmit={start}>
          <h4>Új futás</h4>
          <label>Név<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
          <div className="analysis-form-row">
            <label>Objective<select value={objective} onChange={(event) => setObjective(event.target.value as typeof objective)}><option>CPM</option><option>MODULARITY</option></select></label>
            <label>Resolution<input type="number" min="0.01" max="100" step="0.1" value={resolution} onChange={(event) => setResolution(Number(event.target.value))} /></label>
          </div>
          <div className="analysis-form-row">
            <label>Seed<input type="number" value={seed} onChange={(event) => setSeed(Number(event.target.value))} /></label>
            <label>Min. confidence<input type="number" min="0" max="1" step="0.05" value={minimumConfidence} onChange={(event) => setMinimumConfidence(Number(event.target.value))} /></label>
          </div>
          <label>Hub policy<select value={hubPolicy} onChange={(event) => setHubPolicy(event.target.value as typeof hubPolicy)}><option value="DEGREE_NORMALIZATION">Fokszám-normalizálás</option><option value="NONE">Nincs korrekció</option><option value="EXCLUDE_TOP_HUBS">Top 1% kizárása</option></select></label>
          <label className="checkbox-label"><input type="checkbox" checked={includeTechnicalObjects} onChange={(event) => setIncludeTechnicalObjects(event.target.checked)} />Technikai objektumok bevonása</label>
          {includeTechnicalObjects && <p className="analysis-warning">Az indexek és synonymok torzíthatják a közösséghatárokat.</p>}
          <p className="parameter-hint">Az alapsúlyokat confidence és a választott hub policy korrigálja. Az alapértelmezett profil a logikai objektumokra optimalizált.</p>
          <button className="primary-button" disabled={busy || anyActive || operationActive}>Elemzés indítása</button>
          <button className="secondary-button analysis-profile-button" type="button" onClick={() => void startProfile("resolution")} disabled={busy || anyActive || operationActive}>6 pontos resolution profil</button>
          <button className="secondary-button analysis-profile-button" type="button" onClick={() => void startProfile("seed")} disabled={busy || anyActive || operationActive}>5 seed stabilitásprofil</button>
        </form>

        <div className="analysis-runs">
          <h4>Futások</h4>
          {runs.length === 0 && <p className="muted-copy">Még nincs elemzési futás.</p>}
          {runs.map((run) => (
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
              <div className="quick-rankings">
                <div><span>Legjobb elválasztás</span>{conductanceRanking.slice(0, 3).map((item) => <button key={item.communityId} type="button" onClick={() => void selectCommunity(item.communityId)}>{item.annotation?.name ?? item.suggestedName} · {item.conductance.toFixed(3)}</button>)}</div>
                <div><span>Leggyengébb elválasztás</span>{conductanceRanking.slice(-3).reverse().map((item) => <button key={item.communityId} type="button" onClick={() => void selectCommunity(item.communityId)}>{item.annotation?.name ?? item.suggestedName} · {item.conductance.toFixed(3)}</button>)}</div>
              </div>
              <div className="community-table" role="table" aria-label="Közösségek">
                <div className="community-table-head" role="row"><span>ID</span><span>Node</span><span>Név / séma</span><span>Density</span><span>Conductance</span></div>
                {communities.map((community) => (
                  <button type="button" role="row" key={community.communityId} onClick={() => void selectCommunity(community.communityId)}>
                    <span>#{community.communityId}</span><strong>{community.nodeCount}</strong>
                    <span>{community.annotation?.name ?? community.suggestedName}<small>{community.dominantSchema} · {percent(community.dominantSchemaRatio)} · {community.stability}</small></span>
                    <span>{community.internalDensity.toFixed(3)}</span><span>{community.conductance.toFixed(3)}</span>
                  </button>
                ))}
              </div>
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

      {selectedRun?.summary && communityGraph && (
        <section className="analysis-insight community-workbench">
          <div className="insight-heading"><div><p className="overline">Közösségi térkép</p><h4>Összecsukott gráf és schema–community nézet</h4></div><span>Kattints egy közösségre a „Miért került ide?” részletekhez.</span></div>
          <div className="community-workbench-grid">
            <CommunityGraphCanvas graph={communityGraph} onSelectCommunity={selectCommunity} />
            <div className="schema-matrix-wrap">
              <table className="schema-matrix"><thead><tr><th>Séma</th>{communities.map((item) => <th key={item.communityId}>#{item.communityId}</th>)}</tr></thead><tbody>{schemas.map((schema) => <tr key={schema}><th>{schema}</th>{communities.map((item) => <td key={item.communityId}>{item.schemaDistribution[schema] ?? 0}</td>)}</tr>)}</tbody></table>
            </div>
          </div>
          {communityDetail && (
            <div className="community-detail-card">
              <div>
                <p className="overline">Miért került ide?</p><h4>{communityDetail.annotation?.name ?? communityDetail.metrics.suggestedName}</h4>
                <p>{communityDetail.metrics.nameExplanation}</p>
                <dl><div><dt>Belső/külső súly</dt><dd>{communityDetail.metrics.internalWeight.toFixed(2)} / {communityDetail.metrics.externalWeight.toFixed(2)}</dd></div><div><dt>Stabilitás</dt><dd>{communityDetail.metrics.stability}{communityDetail.metrics.stabilityScore !== undefined ? ` · ${percent(communityDetail.metrics.stabilityScore)}` : ""}</dd></div></dl>
              </div>
              <div><h5>Top belső hubok</h5>{communityDetail.metrics.topInternalHubs.slice(0, 5).map((item) => <code key={item.objectId}>{item.objectId} · {item.strength.toFixed(2)}</code>)}<h5>Top bridge objektumok</h5>{communityDetail.metrics.topBridgeObjects.slice(0, 5).map((item) => <code key={item.objectId}>{item.objectId} · {item.externalStrength.toFixed(2)}</code>)}</div>
              <form onSubmit={(event) => { event.preventDefault(); void saveAnnotation(); }}><h5>Elemzői címke</h5><label>Név<input value={annotationName} onChange={(event) => setAnnotationName(event.target.value)} /></label><label>Megjegyzés<textarea rows={4} value={annotationNote} onChange={(event) => setAnnotationNote(event.target.value)} /></label><button className="primary-button" disabled={busy}>Mentés</button></form>
            </div>
          )}
        </section>
      )}
      {error && <div className="error-banner" role="alert"><strong>Elemzési hiba</strong><span>{error}</span></div>}
    </section>
  );
}
