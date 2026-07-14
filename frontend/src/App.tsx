import { lazy, Suspense, useEffect, useState } from "react";

import {
  ApiError,
  api,
  type Capabilities,
  type PublicConfig,
  type ScanStatus,
  type ScanSummary,
} from "./api/client";
import { StatusPill } from "./components/StatusPill";

const GraphExplorer = lazy(() => import("./components/GraphExplorer").then(
  (module) => ({ default: module.GraphExplorer }),
));

const ACTIVE_SCAN_STATES = new Set([
  "CONNECTING", "DISCOVERING_SCHEMAS", "EXTRACTING_OBJECTS",
  "EXTRACTING_RELATIONSHIPS", "NORMALIZING", "VALIDATING", "PUBLISHING",
]);

function App() {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [selectedSchemas, setSelectedSchemas] = useState<string[]>([]);
  const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null);
  const [scanSummary, setScanSummary] = useState<ScanSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.config().then(setConfig).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "A konfiguráció nem tölthető be.");
    });
  }, []);

  useEffect(() => {
    let disposed = false;
    let summaryLoaded = false;

    async function poll() {
      try {
        const nextStatus = await api.scanStatus();
        if (disposed) return;
        setScanStatus(nextStatus);
        if (ACTIVE_SCAN_STATES.has(nextStatus.state)) {
          summaryLoaded = false;
        } else if (!summaryLoaded) {
          summaryLoaded = true;
          setScanSummary(await api.scanSummary());
        }
      } catch {
        // Configuration and connection actions surface server availability errors.
      }
    }

    void poll();
    const timer = setInterval(poll, 1000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, []);

  async function testConnection() {
    setLoading(true);
    setError(null);
    try {
      const nextCapabilities = await api.testConnection();
      setCapabilities(nextCapabilities);
      setSelectedSchemas((current) => current.filter(
        (schema) => nextCapabilities.schemas.includes(schema),
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

  async function startScan() {
    setLoading(true);
    setError(null);
    try {
      await api.startScan(selectedSchemas);
      setScanStatus(await api.scanStatus());
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Az adatgyűjtés nem indítható el.");
    } finally {
      setLoading(false);
    }
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
  const scanSucceeded = scanStatus?.state === "SUCCEEDED";
  const objectCount = scanSummary
    ? Object.values(scanSummary.objectTypeCounts).reduce((total, count) => total + count, 0)
    : 0;
  const relationshipCount = scanSummary
    ? Object.values(scanSummary.relationshipTypeCounts).reduce((total, count) => total + count, 0)
    : 0;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true"><span /><span /><span /></div>
        <div>
          <p className="eyebrow">Oracle metadata workspace</p>
          <h1>Database Graph Explorer</h1>
        </div>
        <div className="topbar-status">
          <span className="pulse-dot" /> Helyi munkamenet
        </div>
      </header>

      <main>
        <section className="hero">
          <div>
            <p className="step-label">01 · Kapcsolat</p>
            <h2>Térképezd fel az adatbázis<br />láthatatlan szerkezetét.</h2>
            <p className="hero-copy">
              Ellenőrizd a read-only Oracle kapcsolatot, majd válaszd ki az egyetlen közös gráfba kerülő sémákat.
            </p>
          </div>
          <div className="graph-decoration" aria-hidden="true">
            <i className="node node-a" /><i className="node node-b" /><i className="node node-c" />
            <i className="node node-d" /><i className="line line-a" /><i className="line line-b" /><i className="line line-c" />
          </div>
        </section>

        <section className="workspace-grid">
          <article className="card connection-card">
            <div className="card-heading">
              <div>
                <p className="overline">Kapcsolati profil</p>
                <h3>Környezeti konfiguráció</h3>
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
                <div className="radar" aria-hidden="true"><span /><i /></div>
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
                  <p>Válaszd ki a felmérendő sémákat</p>
                  <div>{capabilities.schemas.map((schema) => (
                    <button
                      type="button"
                      className={selectedSchemas.includes(schema) ? "selected" : ""}
                      key={schema}
                      onClick={() => toggleSchema(schema)}
                    >{schema}</button>
                  ))}</div>
                </div>
                {capabilities.warnings.length > 0 && <p className="warning">{capabilities.warnings.length} katalógusnézet nem olvasható.</p>}
              </>
            )}
          </article>
        </section>

        {error && <div className="error-banner" role="alert"><strong>Műveleti hiba</strong><span>{error}</span></div>}

        <section className="scan-panel">
          <div className="scan-heading">
            <span className="scan-number">02</span>
            <div><p className="overline">Metaadatgyűjtés</p><h3>Többsémás forrásgráf</h3></div>
            <StatusPill ok={scanStatus?.state === "SUCCEEDED"}>
              {scanStatus?.state ?? "IDLE"}
            </StatusPill>
          </div>
          <div className="scan-actions">
            <div><strong>{selectedSchemas.length}</strong><span>kiválasztott séma</span></div>
            <button
              className="primary-button"
              onClick={startScan}
              disabled={selectedSchemas.length === 0 || scanActive || loading}
            >Adatgyűjtés indítása</button>
            {scanActive && <button className="secondary-button" onClick={cancelScan}>Megszakítás</button>}
          </div>
          {scanStatus && scanStatus.state !== "IDLE" && (
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
          {scanSummary && (
            <div className="scan-summary">
              <div><span>Objektum</span><strong>{objectCount.toLocaleString("hu-HU")}</strong></div>
              <div><span>Kapcsolat</span><strong>{relationshipCount.toLocaleString("hu-HU")}</strong></div>
              <div><span>Külső cél</span><strong>{scanSummary.externalObjectCount.toLocaleString("hu-HU")}</strong></div>
              <div><span>Feldolgozott séma</span><strong>{scanSummary.selectedSchemas.length}</strong></div>
            </div>
          )}
        </section>
        <Suspense fallback={<div className="explorer-loading">Gráfböngésző betöltése…</div>}>
          <GraphExplorer />
        </Suspense>
      </main>
    </div>
  );
}

export default App;
