import { useEffect, useState } from "react";

import { ApiError, api, type Capabilities, type PublicConfig } from "./api/client";
import { StatusPill } from "./components/StatusPill";

function App() {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.config().then(setConfig).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "A konfiguráció nem tölthető be.");
    });
  }, []);

  async function testConnection() {
    setLoading(true);
    setError(null);
    try {
      setCapabilities(await api.testConnection());
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
                  <p>Első elérhető sémák</p>
                  <div>{capabilities.schemas.slice(0, 12).map((schema) => <span key={schema}>{schema}</span>)}</div>
                </div>
                {capabilities.warnings.length > 0 && <p className="warning">{capabilities.warnings.length} katalógusnézet nem olvasható.</p>}
              </>
            )}
          </article>
        </section>

        {error && <div className="error-banner" role="alert"><strong>Kapcsolati hiba</strong><span>{error}</span></div>}

        <section className="next-step">
          <span>02</span><div><p>következő mérföldkő</p><h3>Többsémás metaadatgyűjtés</h3></div>
          <p>Objektumok, függőségek, idegen kulcsok és bizonyítékok atomikus betöltése.</p>
        </section>
      </main>
    </div>
  );
}

export default App;
