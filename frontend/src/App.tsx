import { lazy, Suspense, useEffect, useState } from "react";

import {
  ApiError,
  api,
  type Capabilities,
  type PublicConfig,
  type ScanStatus,
  type ScanSummary,
  type NamedSubgraph,
} from "./api/client";
import { StatusPill } from "./components/StatusPill";
import { ConnectionIllustration, HeroGraphIllustration } from "./components/GraphIllustration";

const GraphExplorer = lazy(() => import("./components/GraphExplorer").then(
  (module) => ({ default: module.GraphExplorer }),
));
const AnalysisPanel = lazy(() => import("./components/AnalysisPanel").then(
  (module) => ({ default: module.AnalysisPanel }),
));

const ACTIVE_SCAN_STATES = new Set([
  "CONNECTING", "DISCOVERING_SCHEMAS", "EXTRACTING_OBJECTS",
  "EXTRACTING_RELATIONSHIPS", "NORMALIZING", "VALIDATING", "PUBLISHING",
]);
const ACTIVE_ANALYSIS_STATES = new Set([
  "PREPARING_ANALYSIS", "DETECTING_COMMUNITIES",
  "CALCULATING_METRICS", "SAVING_RESULTS", "ASSESSING_STABILITY",
]);
const ACTIVE_TASK_STATES = new Set([
  ...ACTIVE_SCAN_STATES,
  ...ACTIVE_ANALYSIS_STATES,
  "EXPORTING",
]);

function App() {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [selectedSchemas, setSelectedSchemas] = useState<string[]>([]);
  const [selectedObjectTypes, setSelectedObjectTypes] = useState<string[]>([]);
  const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null);
  const [scanSummary, setScanSummary] = useState<ScanSummary | null>(null);
  const [scanRevision, setScanRevision] = useState(0);
  const [activeSubgraph, setActiveSubgraph] = useState<NamedSubgraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.config().then(setConfig).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "A konfiguráció nem tölthető be.");
    });
  }, []);

  useEffect(() => {
    let disposed = false;
    async function loadInitialStatus() {
      try {
        const nextStatus = await api.scanStatus();
        if (disposed) return;
        setScanStatus(nextStatus);
        if (!ACTIVE_TASK_STATES.has(nextStatus.state)) {
          const nextSummary = await api.scanSummary();
          if (!disposed) setScanSummary(nextSummary);
        }
      } catch {
        // Configuration and connection actions surface server availability errors.
      }
    }
    void loadInitialStatus();
    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    if (!scanStatus || !ACTIVE_TASK_STATES.has(scanStatus.state)) return;
    let disposed = false;
    const scanWasActive = ACTIVE_SCAN_STATES.has(scanStatus.state);
    async function poll() {
      try {
        const nextStatus = await api.scanStatus();
        if (disposed) return;
        setScanStatus(nextStatus);
        if (scanWasActive && !ACTIVE_SCAN_STATES.has(nextStatus.state)) {
          const nextSummary = await api.scanSummary();
          if (!disposed) {
            setScanSummary(nextSummary);
            setScanRevision((current) => current + 1);
          }
        }
      } catch {
        // A következő aktív polling kör újrapróbálja.
      }
    }
    const timer = setInterval(() => { void poll(); }, 1000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [scanStatus?.state]);

  async function testConnection() {
    setLoading(true);
    setError(null);
    try {
      const nextCapabilities = await api.testConnection();
      setCapabilities(nextCapabilities);
      setSelectedSchemas((current) => current.filter(
        (schema) => nextCapabilities.schemas.includes(schema),
      ));
      setSelectedObjectTypes((current) => current.filter(
        (objectType) => nextCapabilities.objectTypes.includes(objectType),
      ));
    } catch (reason) {
      if (reason instanceof ApiError) {
        const detailMessage = reason.details.oracleMessage ?? reason.details.networkMessage;
        const hint = reason.details.hint;
        setError(
          `${reason.message}`
          + `${typeof detailMessage === "string" ? ` ${detailMessage}` : ""}`
          + `${typeof hint === "string" ? ` ${hint}` : ""}`,
        );
      } else {
        setError("A kapcsolatpróba váratlan hibával leállt.");
      }
    } finally {
      setLoading(false);
    }
  }

  function toggleSchema(schema: string) {
    setSelectedSchemas((current) => current.includes(schema)
      ? current.filter((item) => item !== schema)
      : [...current, schema]);
  }

  function toggleObjectType(objectType: string) {
    setSelectedObjectTypes((current) => current.includes(objectType)
      ? current.filter((item) => item !== objectType)
      : [...current, objectType]);
  }

  async function startScan() {
    setLoading(true);
    setError(null);
    try {
      await api.startScan(selectedSchemas, selectedObjectTypes);
      setScanStatus(await api.scanStatus());
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Az adatgyűjtés nem indítható el.");
    } finally {
      setLoading(false);
    }
  }

  async function resetWorkspace() {
    if (!window.confirm("Minden kinyert metaadat, részgráf, elemzés, megjegyzés és export törlődik. Folytatod?")) return;
    setLoading(true); setError(null);
    try {
      await api.resetWorkspace();
      setCapabilities(null);
      setSelectedSchemas([]); setSelectedObjectTypes([]);
      setScanSummary(null); setScanStatus(null); setActiveSubgraph(null);
      setScanRevision((current) => current + 1);
      setConfig((current) => current ? {
        ...current, datasetId: null, resetRequired: false, activeOperation: false,
      } : current);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "A munkaterület nem törölhető.");
    } finally { setLoading(false); }
  }

  async function cancelScan() {
    try {
      await api.cancelScan();
      setScanStatus(await api.scanStatus());
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Az adatgyűjtés nem szakítható meg.");
    }
  }

  const scanActive = Boolean(scanStatus && ACTIVE_SCAN_STATES.has(scanStatus.state));
  const analysisActive = Boolean(scanStatus && ACTIVE_ANALYSIS_STATES.has(scanStatus.state));
  const exportActive = scanStatus?.state === "EXPORTING";
  const lastOperationWasAnalysis = Boolean(
    scanStatus?.phase && ACTIVE_ANALYSIS_STATES.has(scanStatus.phase),
  );
  const lastOperationWasExport = scanStatus?.phase === "EXPORTING";
  const scanSucceeded = scanStatus?.state === "SUCCEEDED"
    && !lastOperationWasAnalysis
    && !lastOperationWasExport;
  const scanDisplayState = analysisActive
    ? "ELEMZÉS FUT"
    : exportActive ? "EXPORT FUT"
    : lastOperationWasAnalysis || lastOperationWasExport ? "IDLE" : scanStatus?.state ?? "IDLE";
  const objectCount = scanSummary
    ? Object.values(scanSummary.objectTypeCounts).reduce((total, count) => total + count, 0)
    : 0;
  const relationshipCount = scanSummary
    ? Object.values(scanSummary.relationshipTypeCounts).reduce((total, count) => total + count, 0)
    : 0;
  const workflowStep = scanSummary ? (activeSubgraph ? 4 : 3) : capabilities ? 2 : 1;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Ugrás a fő tartalomra</a>
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true"><span /><span /><span /></div>
        <div className="brand-copy">
          <p className="eyebrow">Oracle metadata workspace</p>
          <h1>Adatbázis-gráf elemző</h1>
        </div>
        <nav className="topbar-nav" aria-label="Fő navigáció">
          <a href="#connection">Kapcsolat</a>
          <a href="#scan">Adatgyűjtés</a>
          <a href="#graph">Gráf</a>
          <a href="#analysis">Elemzés</a>
        </nav>
        <div className="topbar-status">
          <span className="pulse-dot" /> Helyi munkamenet
        </div>
      </header>

      <main id="main-content">
        <section className="hero">
          <div className="hero-content">
            <p className="step-label">Oracle struktúrafelmérés</p>
            <h2>Lásd át, mi mivel<br />függ össze.</h2>
            <p className="hero-copy">
              Kapcsolódj biztonságosan, gyűjtsd össze a metaadatokat, majd fedezd fel és elemezd az adatbázis valódi szerkezetét egyetlen munkafelületen.
            </p>
          </div>
          <div className="graph-decoration">
            <HeroGraphIllustration />
          </div>
        </section>

        <nav className="workflow-nav" aria-label="Felmérési folyamat">
          {[
            [1, "Kapcsolat", "Ellenőrzés és sémaválasztás", "connection"],
            [2, "Adatgyűjtés", "A forrásgráf elkészítése", "scan"],
            [3, "Gráf", "Komponensek kiválasztása", "graph"],
            [4, "Elemzés", "Közösségek feltárása", "analysis"],
          ].map(([step, title, description, target]) => (
            <a
              key={String(step)}
              href={`#${target}`}
              className={`${Number(step) < workflowStep ? "complete" : ""} ${Number(step) === workflowStep ? "current" : ""}`}
              aria-current={Number(step) === workflowStep ? "step" : undefined}
            >
              <span>{Number(step) < workflowStep ? "✓" : String(step).padStart(2, "0")}</span>
              <strong>{title}</strong>
              <small>{description}</small>
            </a>
          ))}
        </nav>

        <section className="workspace-grid" id="connection" aria-labelledby="connection-title">
          <article className="card connection-card">
            <div className="card-heading">
              <div>
                <p className="overline">01 · Kapcsolat</p>
                <h3 id="connection-title">Kapcsolati beállítások</h3>
              </div>
              <StatusPill ok={Boolean(config?.oracleConfigured)}>
                {config?.oracleConfigured ? "Beállítva" : "Hiányos"}
              </StatusPill>
            </div>

            <dl className="config-list">
              <div><dt>Kapcsolódási mód</dt><dd>{config?.oracleMode?.toUpperCase() ?? "—"}</dd></div>
              <div><dt>Hitelesítés</dt><dd>{config?.oracleConfigured ? "ORACLE_USER / PASSWORD" : "Add meg a .env fájlban"}</dd></div>
              <div><dt>Adatfájl</dt><dd>{config?.dataFilePresent ? "Inicializálva" : "Indításkor létrejön"}</dd></div>
            </dl>

            <button className="primary-button" onClick={testConnection} disabled={!config?.oracleConfigured || loading}>
              {loading ? <span className="spinner" aria-hidden="true" /> : <span className="button-icon" aria-hidden="true">↗</span>}
              {loading ? "Kapcsolódás…" : "Kapcsolat tesztelése"}
            </button>
            <p className="security-note">A hitelesítési adatok nem kerülnek SQLite-ba, API-válaszba vagy naplóba.</p>
          </article>

          <article className={`card result-card ${capabilities ? "result-card--ready" : ""}`}>
            {!capabilities ? (
              <div className="empty-state">
                <ConnectionIllustration />
                <h3>Kapcsolatra vár</h3>
                <p>A sikeres teszt után itt jelenik meg a verzió, a container és a látható sémák összesítése.</p>
              </div>
            ) : (
              <>
                <div className="card-heading">
                  <div><p className="overline">Élő kapcsolat</p><h3>{capabilities.databaseName}</h3></div>
                  <StatusPill ok>Elérhető</StatusPill>
                </div>
                <div className="metric-row">
                  <div><span>Oracle</span><strong>{capabilities.oracleVersion}</strong></div>
                  <div><span>Container / PDB</span><strong>{capabilities.containerName}</strong></div>
                  <div><span>Látható sémák</span><strong>{capabilities.schemas.length}</strong></div>
                </div>
                <div className="schema-preview">
                  <div className="selection-heading">
                    <p>Felmérendő sémák</p>
                    <span>{selectedSchemas.length} / {capabilities.schemas.length} kijelölve</span>
                  </div>
                  <div className="selection-actions">
                    <button type="button" onClick={() => setSelectedSchemas(capabilities.schemas)}>Mind kijelölése</button>
                    <button type="button" onClick={() => setSelectedSchemas([])}>Kijelölés törlése</button>
                  </div>
                  <div>{capabilities.schemas.map((schema) => (
                    <button
                      type="button"
                      className={selectedSchemas.includes(schema) ? "selected" : ""}
                      key={schema}
                      aria-pressed={selectedSchemas.includes(schema)}
                      onClick={() => toggleSchema(schema)}
                    >{schema}</button>
                  ))}</div>
                </div>
                <details className="schema-preview">
                  <summary>Objektumtípus-szűrés · {selectedObjectTypes.length || "minden"}</summary>
                  <div>
                    <button
                        type="button"
                        className={selectedObjectTypes.length === 0 ? "selected" : ""}
                        aria-pressed={selectedObjectTypes.length === 0}
                        onClick={() => setSelectedObjectTypes([])}
                    >Minden típus</button>
                    {capabilities.objectTypes.map((objectType) => (
                      <button
                        type="button"
                        className={selectedObjectTypes.includes(objectType) ? "selected" : ""}
                        key={objectType}
                        aria-pressed={selectedObjectTypes.includes(objectType)}
                        onClick={() => toggleObjectType(objectType)}
                      >{objectType}</button>
                    ))}
                  </div>
                </details>
                {capabilities.warnings.length > 0 && <p className="warning">{capabilities.warnings.length} katalógusnézet nem olvasható.</p>}
              </>
            )}
          </article>
        </section>

        {error && <div className="error-banner" role="alert"><strong>Műveleti hiba</strong><span>{error}</span></div>}

        <section className="scan-panel" id="scan" aria-labelledby="scan-title">
          <div className="scan-heading">
            <span className="scan-number">02</span>
            <div><p className="overline">Metaadatgyűjtés</p><h3 id="scan-title">Többsémás forrásgráf</h3></div>
            <div className="section-heading-actions">
              <StatusPill ok={scanSucceeded}>{scanDisplayState}</StatusPill>
              <button className="danger-button danger-button--quiet" type="button" onClick={() => void resetWorkspace()} disabled={scanActive || analysisActive || exportActive || loading}>Új felmérés · minden adat törlése</button>
            </div>
          </div>
          <div className="scan-actions">
            <div className="scan-action-metric"><strong>{selectedSchemas.length}</strong><span>kiválasztott séma</span></div>
            <div className="scan-action-metric"><strong>{selectedObjectTypes.length || "Mind"}</strong><span>objektumtípus</span></div>
            <button
              className="primary-button"
              onClick={startScan}
              disabled={selectedSchemas.length === 0 || Boolean(scanSummary) || scanActive || analysisActive || exportActive || loading}
            >Adatgyűjtés indítása</button>
            {scanActive && <button className="secondary-button" onClick={cancelScan}>Megszakítás</button>}
          </div>
          {!scanSummary && selectedSchemas.length === 0 && <p className="action-hint">Az indításhoz előbb teszteld a kapcsolatot, majd jelölj ki legalább egy sémát.</p>}
          {scanSummary && <p className="operation-note">Új metaadatgyűjtés előtt indíts új felmérést. Ez megakadályozza a korábbi és az új adathalmaz keveredését.</p>}
          {scanStatus && (scanActive || scanSucceeded) && (
            <div className="scan-progress" aria-live="polite">
              {!scanSucceeded && (
                <div><span>{scanStatus.phase}</span><strong>{scanStatus.message}</strong></div>
              )}
              <progress
                aria-label={scanSucceeded ? "Adatgyűjtés befejezve" : "Adatgyűjtés folyamatban"}
                value={scanSucceeded
                  ? 1
                  : scanStatus.progress_total ? scanStatus.progress_current : undefined}
                max={scanSucceeded ? 1 : scanStatus.progress_total ?? 1}
              />
              {scanStatus.error_message && <p className="warning">{scanStatus.error_message}</p>}
            </div>
          )}
          {analysisActive && <p className="operation-note">Közösségelemzés fut; új adatgyűjtés csak a befejezése után indítható.</p>}
          {exportActive && <p className="operation-note">Export készül; új hosszú művelet csak a befejezése után indítható.</p>}
          {scanSummary && (
            <>
              <div className="scan-summary">
                <div><span>Objektum</span><strong>{objectCount.toLocaleString("hu-HU")}</strong></div>
                <div><span>Kapcsolat</span><strong>{relationshipCount.toLocaleString("hu-HU")}</strong></div>
                <div><span>Külső cél</span><strong>{scanSummary.externalObjectCount.toLocaleString("hu-HU")}</strong></div>
                <div><span>Feldolgozott séma</span><strong>{scanSummary.selectedSchemas.length}</strong></div>
              </div>
              <details className="scan-coverage">
                <summary>Lefedettségi részletek</summary>
                <div>
                  <section><h4>Owner szerint</h4><ul>{Object.entries(scanSummary.ownerCounts).map(([owner, count]) => <li key={owner}><span>{owner}</span><strong>{count}</strong></li>)}</ul></section>
                  <section><h4>Objektumtípus szerint</h4><ul>{Object.entries(scanSummary.objectTypeCounts).map(([objectType, count]) => <li key={objectType}><span>{objectType}</span><strong>{count}</strong></li>)}</ul></section>
                  <section><h4>Kapcsolattípus szerint</h4><ul>{Object.entries(scanSummary.relationshipTypeCounts).map(([relationshipType, count]) => <li key={relationshipType}><span>{relationshipType}</span><strong>{count}</strong></li>)}</ul></section>
                </div>
                {scanSummary.unresolvedSynonymCount > 0 && <p className="warning">Fel nem oldott synonym: {scanSummary.unresolvedSynonymCount}</p>}
                {scanSummary.warnings.map((warning) => <p className="warning" key={warning}>{warning}</p>)}
              </details>
            </>
          )}
        </section>
        <Suspense fallback={<div className="explorer-loading">Gráfböngésző betöltése…</div>}>
          <GraphExplorer
            key={`graph-${scanRevision}`}
            dataVersion={scanSummary
              ? (scanSummary.datasetId ?? "published-dataset")
              : (lastOperationWasExport || lastOperationWasAnalysis ? null : scanStatus?.finished_at)}
            activeSubgraph={activeSubgraph}
            onSelectSubgraph={setActiveSubgraph}
          />
        </Suspense>
        <Suspense fallback={<div className="explorer-loading">Elemzőfelület betöltése…</div>}>
          <AnalysisPanel
            key={`analysis-${scanRevision}`}
            operationActive={scanActive || analysisActive || exportActive}
            sourceRevision={scanRevision}
            activeSubgraph={activeSubgraph}
            onSubgraphCreated={setActiveSubgraph}
          />
        </Suspense>
      </main>
    </div>
  );
}

export default App;
