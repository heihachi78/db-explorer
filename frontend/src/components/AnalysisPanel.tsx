import { useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  api,
  type AnalysisRun,
  type CommunityMetrics,
} from "../api/client";


const ACTIVE_ANALYSIS_STATES = new Set(["QUEUED", "RUNNING"]);

function percent(value: number | undefined) {
  return value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;
}

export function AnalysisPanel({ operationActive = false }: { operationActive?: boolean }) {
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<AnalysisRun | null>(null);
  const [communities, setCommunities] = useState<CommunityMetrics[]>([]);
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
      // The global configuration panel already reports server availability.
    }
  }

  useEffect(() => {
    let disposed = false;
    async function poll() {
      if (!disposed) await refresh();
    }
    void poll();
    const timer = setInterval(poll, 2000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, []);

  async function start(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.startAnalysis({
        name, objective, resolution, seed, minimumConfidence,
        hubPolicy, includeTechnicalObjects,
      });
      await refresh();
      setSelectedRun({
        id: result.analysisId, name, status: "QUEUED", algorithm: "LEIDEN",
        config: {}, summary: null, errorMessage: null,
        createdAt: new Date().toISOString(), startedAt: null, finishedAt: null,
      });
      setCommunities([]);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Az elemzés nem indítható el.");
    } finally {
      setBusy(false);
    }
  }

  async function startProfile() {
    setBusy(true);
    setError(null);
    try {
      await api.startResolutionProfile({
        name: `${name} profil`, objective, seed, minimumConfidence,
        hubPolicy, includeTechnicalObjects,
      });
      await refresh();
      setSelectedRun(null);
      setCommunities([]);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A resolution profil nem indítható el.");
    } finally {
      setBusy(false);
    }
  }

  async function inspect(run: AnalysisRun) {
    setSelectedRun(run);
    setCommunities([]);
    if (run.status !== "SUCCEEDED") return;
    setBusy(true);
    try {
      setCommunities(await api.communities(run.id));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A közösségek nem tölthetők be.");
    } finally {
      setBusy(false);
    }
  }

  async function cancel(run: AnalysisRun) {
    try {
      await api.cancelAnalysis(run.id);
      await refresh();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Az elemzés nem szakítható meg.");
    }
  }

  async function remove(run: AnalysisRun) {
    try {
      await api.deleteAnalysis(run.id);
      if (selectedRun?.id === run.id) {
        setSelectedRun(null);
        setCommunities([]);
      }
      await refresh();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Az elemzés nem törölhető.");
    }
  }

  const anyActive = runs.some((run) => ACTIVE_ANALYSIS_STATES.has(run.status));

  return (
    <section className="analysis-panel">
      <div className="scan-heading">
        <span className="scan-number">04</span>
        <div><p className="overline">Közösségelemzés</p><h3>Leiden futások és mutatók</h3></div>
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
          <button className="primary-button" disabled={busy || anyActive || operationActive}>Elemzés indítása</button>
          <button className="secondary-button analysis-profile-button" type="button" onClick={() => void startProfile()} disabled={busy || anyActive || operationActive}>6 pontos resolution profil</button>
        </form>

        <div className="analysis-runs">
          <h4>Futások</h4>
          {runs.length === 0 && <p className="muted-copy">Még nincs elemzési futás.</p>}
          {runs.map((run) => (
            <article key={run.id} className={selectedRun?.id === run.id ? "selected" : ""}>
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
              <div className="community-table" role="table" aria-label="Közösségek">
                <div className="community-table-head" role="row"><span>ID</span><span>Node</span><span>Domináns séma</span><span>Density</span><span>Conductance</span></div>
                {communities.map((community) => (
                  <div role="row" key={community.communityId}>
                    <span>#{community.communityId}</span><strong>{community.nodeCount}</strong>
                    <span>{community.dominantSchema} · {percent(community.dominantSchemaRatio)}</span>
                    <span>{community.internalDensity.toFixed(3)}</span>
                    <span>{community.conductance.toFixed(3)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
      {error && <div className="error-banner" role="alert"><strong>Elemzési hiba</strong><span>{error}</span></div>}
    </section>
  );
}
