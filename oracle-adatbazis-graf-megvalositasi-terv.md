# Oracle adatbázis-objektumgráf és elemzőalkalmazás – részletes megvalósítási terv

**Dokumentum állapota:** megvalósításra előkészített terv

**Dátum:** 2026-07-14

**Cél:** egyszeri, egyfelhasználós Oracle-adatbázis-felmérés támogatása
**Becsült megvalósítás:** 9–10 hét kis fejlesztőcsapattal

## 1. Az alkalmazás ötlete röviden

Az alkalmazás egyetlen Oracle-adatbázis kiválasztott – már az első verzióban több – sémájából kiolvassa az adatbázis-objektumokat és a közöttük lévő kapcsolatokat. Ezekből gráfot épít, amelyben az objektumok a csúcsok, a függőségek, idegen kulcsok és más hivatkozások pedig az élek.

A felmérést végző egyetlen felhasználó az alkalmazásban:

- megkeresheti és vizuálisan bejárhatja az objektumokat;
- megvizsgálhatja egy objektum bejövő és kimenő függőségeit;
- közösségdetektálással egymással erősen összekapcsolt objektumcsoportokat kereshet;
- összehasonlíthat több súlyozási, hubkezelési és Leiden-resolution beállítást;
- azonosíthat központi, megosztott és különböző csoportokat összekötő objektumokat;
- hatás- és útvonalelemzést végezhet;
- az eredményeket JSON, CSV, SVG vagy PNG formában exportálhatja.

Az alkalmazás helyben, Docker Compose segítségével fut. Nincs belépés, felhasználó- vagy jogosultságkezelés, külön alkalmazás-adatbázis-szerver, ütemezett működés vagy vállalati üzemeltetési infrastruktúra. Az aktuális felmérés adatai egyetlen SQLite-fájlban találhatók.

## 2. Célok, sikerkritériumok és határok

### 2.1. Célok

- A dokumentálatlan Oracle-rendszer logikai és technikai szerkezetének automatikus feltárása.
- Több séma objektumainak egyetlen közös gráfban történő kezelése.
- Feltételezett alkalmazásmodulok vagy üzleti domének felismerése.
- A sémák és a ténylegesen detektált objektumközösségek kapcsolatának vizsgálata.
- Kritikus hubok, bridge objektumok és túlzottan összekapcsolt komponensek azonosítása.
- Egy objektum módosításának lehetséges hatását és függőségi útvonalait feltáró eszköz biztosítása.
- A közösségdetektálás paramétereinek interaktív kísérletezésével az elemző munkájának gyorsítása.
- A számítások eredetének és beállításainak megőrzése az aktuális felmérésen belül.

### 2.2. Mérhető sikerkritériumok

| Terület | Célérték |
|---|---:|
| Kiválasztott sémák objektumainak lefedettsége | legalább 95% a támogatott típusokra |
| Katalógusból származó kapcsolatok pontossága | legalább 99% kézi kontrollmintán |
| Azonos nevű, eltérő sémájú objektumok elkülönítése | 100% |
| Sémák közötti FK- és dependency-kapcsolatok megőrzése | 100% a látható katalógusadatok alapján |
| Objektumkeresés | 500 ms alatt tipikus helyi gépen |
| Korlátozott 1–2 mélységű részgráf | 1 másodperc alatt tipikus adathalmazon |
| Elemzés reprodukálhatósága | azonos adat + konfiguráció + seed esetén azonos eredmény |
| Oracle-adatbázis módosítása | soha; kizárólag olvasás |
| Felhasználói indítás | egyetlen `docker compose up --build` paranccsal |

A nagy gráfokra vonatkozó idő- és memóriahatárokat az első valós adatkivonaton kell pontosítani.

### 2.3. Nem cél

- Oracle-objektumok létrehozása, módosítása vagy törlése.
- Valós idejű vagy automatikusan ütemezett szinkronizáció.
- Korábbi felmérések tartós archiválása vagy automatikus összehasonlítása.
- Több külön Oracle-adatbázis egyidejű kezelése.
- Több felhasználó, belépés, szerepkörök vagy alkalmazásszintű jogosultságok.
- Külön PostgreSQL-, Neo4j-, Redis- vagy queue-szolgáltatás.
- Dinamikusan előállított SQL minden hivatkozásának biztos felismerése.
- A detektált közösségek automatikus, tévedhetetlen azonosítása üzleti modulokkal.

## 3. A felhasználó teljes munkafolyamata

1. A felhasználó kitölti a helyi `.env` fájlt az Oracle kapcsolati adataival.
2. Elindítja az alkalmazást Docker Compose-zal.
3. Kapcsolatpróbát futtat; az alkalmazás megmutatja az Oracle-verziót, PDB/container nevet és az elérhető sémákat.
4. Kiválasztja a felmérendő sémákat és az opcionális objektumtípus-szűrést.
5. Elindítja az adatgyűjtést, és fázisonként látja az előrehaladást.
6. Sikeres gyűjtés után áttekinti az objektum- és kapcsolatszámokat, illetve az esetleges lefedettségi figyelmeztetéseket.
7. Objektumokra keres, részgráfokat nyit és kapcsolatokat vizsgál.
8. Lefuttatja az alapértelmezett Leiden-elemzést.
9. Több resolution-, súly- és hubkezelési beállítást próbál ki.
10. Összehasonlítja a közösségek számát, méretét, conductance-ét, stabilitását és értelmezhetőségét.
11. Megvizsgálja a közösségek központi és kifelé kapcsoló objektumait.
12. Szükség szerint helyi nevet vagy megjegyzést rendel a közösségekhez.
13. Hatás- és útvonalelemzéseket futtat.
14. Exportálja a kiválasztott eredményeket.
15. Ha az Oracle-adatbázis megváltozik, kézzel újraindítja a teljes gyűjtést; a sikeres új futás lecseréli a korábbi adathalmazt.

## 4. Architektúra

```text
┌───────────────────────────────────────────────────────────────┐
│ Böngésző                                                      │
│ React + TypeScript + Cytoscape.js                             │
│ keresés | gráf | közösségek | útvonal | hatás | export       │
└───────────────────────────┬───────────────────────────────────┘
                            │ HTTP / REST + állapot-polling
┌───────────────────────────▼───────────────────────────────────┐
│ Egyetlen FastAPI alkalmazás                                  │
│ API + statikus frontend + in-process háttérfeladatok          │
│                                                               │
│ Oracle scanner → normalizálás → gráfépítés → igraph elemzés   │
└───────────────┬───────────────────────────────┬───────────────┘
                │                               │
        read-only Oracle                  helyi SQLite
        python-oracledb                   /data/oracle_graph.db
```

### 4.1. Technológiai döntések

- **Frontend:** React, TypeScript, Vite, Cytoscape.js.
- **Backend:** Python, FastAPI, Pydantic.
- **Oracle kapcsolat:** `python-oracledb`, alapértelmezetten Thin mód.
- **Helyi tárolás:** Python beépített `sqlite3` modulja és egyetlen SQLite-fájl.
- **Gráfelemzés:** `python-igraph`; Leiden elsődlegesen a beépített `community_leiden` implementációval.
- **Speciális Leiden-funkció:** `leidenalg` csak resolution-profile vagy speciális partition esetén.
- **Futtatás:** egy Docker image és egy Docker Compose szolgáltatás.
- **Frontend kiszolgálás:** a buildelt frontend statikus fájljait a FastAPI szolgálja ki.
- **Hosszú műveletek:** egyetlen folyamaton belüli háttértask; nincs Celery, Redis vagy külön worker.

### 4.2. Folyamatkorlátok

- Az alkalmazás egyetlen Uvicorn workerrel fusson, hogy az in-process feladatállapot egyértelmű legyen.
- Egyszerre legfeljebb egy adatgyűjtés vagy számításigényes elemzés futhat.
- Az olvasási API-k az adatgyűjtés közben a korábbi sikeres SQLite-fájlt használhatják.
- A frontend pollinggal kérdezze le a scan vagy elemzés állapotát; WebSocket/SSE nem szükséges.
- Leállításkor a folyamatban lévő művelet megszakított állapotot kap; az aktuális sikeres adatfájl nem sérülhet.

## 5. Monorepo-struktúra

```text
oracle-graph-analyzer/
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── features/
│   │   │   ├── scan/
│   │   │   ├── objects/
│   │   │   ├── graph/
│   │   │   ├── communities/
│   │   │   └── analysis/
│   │   └── styles/
│   ├── tests/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── config.py
│   │   ├── oracle/
│   │   │   ├── connection.py
│   │   │   ├── capabilities.py
│   │   │   ├── queries/
│   │   │   └── extractors/
│   │   ├── graph/
│   │   │   ├── models.py
│   │   │   ├── normalization.py
│   │   │   ├── builder.py
│   │   │   ├── traversal.py
│   │   │   └── metrics.py
│   │   ├── analysis/
│   │   │   ├── preprocessing.py
│   │   │   ├── communities.py
│   │   │   ├── centrality.py
│   │   │   └── comparison.py
│   │   ├── persistence/
│   │   │   ├── database.py
│   │   │   ├── schema.sql
│   │   │   └── repositories.py
│   │   └── tasks/
│   ├── tests/
│   └── pyproject.toml
├── data/
│   └── .gitkeep
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

Fejlesztéskor a frontend és backend külön indítható, de a felmérést végző felhasználó számára csak a Docker Compose-os, egy szolgáltatásból álló futtatás dokumentálandó.

## 6. Helyi SQLite-adatmodell

### 6.1. Táblák

| Tábla | Tartalom |
|---|---|
| `app_meta` | schema version, adatbázisazonosító, scan ideje, kiválasztott sémák |
| `scan_status` | aktuális művelet állapota, fázisa, számlálói és hibaüzenete |
| `objects` | az aktuális felmérés normalizált Oracle-objektumai |
| `relationships` | nyers, irányított és típusos kapcsolatok |
| `relationship_evidence` | a kapcsolat forrása és bizonyítéka |
| `object_details` | típusfüggő részletek JSON-ként vagy külön oszlopokban |
| `analysis_runs` | az aktuális adathalmazon futtatott elemzések konfigurációi |
| `analysis_membership` | objektum és közösség megfeleltetés |
| `community_metrics` | közösségenként számított mutatók |
| `community_edges` | közösségek közötti aggregált élek |
| `centrality_results` | elemzésenkénti központisági értékek |
| `annotations` | helyi közösségnév és elemzői megjegyzés |

### 6.2. Kötelező indexek

- `objects(owner, object_type, name)`;
- `objects(name)`;
- `relationships(source_id)`;
- `relationships(target_id)`;
- `relationships(relationship_type)`;
- `analysis_membership(analysis_id, community_id)`;
- `analysis_membership(analysis_id, object_id)`;
- `community_edges(analysis_id, source_community, target_community)`.

SQLite `WAL` mód használható az olvasási műveletek folyamatosságához. A gráfelemzés előtt a szükséges node- és edge-lista egyszer töltődjön memóriába; ne sok apró SQLite-lekérdezésből épüljön fel az igraph objektum.

### 6.3. Felülírás biztonságos megvalósítása

Az új adatgyűjtés ne írjon közvetlenül az aktuális fájlba:

1. létrejön a `/data/oracle_graph.next.db`;
2. minden kinyert és normalizált adat ebbe kerül;
3. lefutnak az idegenkulcs-, node/edge- és SQLite `integrity_check` ellenőrzések;
4. siker esetén minden kapcsolat bezárul;
5. `os.replace()` atomikusan a helyére teszi az új fájlt;
6. az alkalmazás újranyitja az aktuális adatbázist;
7. sikertelen vagy megszakított futásnál a `.next.db` törölhető, a korábbi sikeres fájl megmarad.

Az új adatgyűjtés a korábbi elemzési futásokat és megjegyzéseket is lecseréli. Az aktuális adathalmazon belül azonban több analysis run megőrizhető, hogy a paraméterek összehasonlíthatók legyenek.

## 7. Oracle-kapcsolat és több séma kezelése

### 7.1. Helyi konfiguráció

```dotenv
ORACLE_USER=metadata_reader
ORACLE_PASSWORD=...
ORACLE_DSN=db-host:1521/SERVICE_NAME
ORACLE_MODE=thin
APP_PORT=8000
```

A jelszó csak a helyi `.env` fájlban vagy Docker secretként jelenjen meg. Ne kerüljön SQLite-ba, API-válaszba, exportba vagy logba.

### 7.2. Kapcsolatpróba és capabilities

A kapcsolatpróba adja vissza:

- Oracle-verzió;
- adatbázis és container/PDB neve;
- Thin/Thick mód;
- elérhető sémák;
- olvasható `ALL_*` vagy – ha külön engedélyezett – `DBA_*` nézetek;
- elérhető objektumtípusok;
- `DBMS_METADATA.GET_DDL` használhatósága;
- figyelmeztetések a hiányzó nézetjogokra.

Az első verzió alapértelmezett scope-ja `ALL_*`. A kiválasztott sémák listája minden releváns lekérdezésben bind változóként szerepeljen.

### 7.3. Több séma szabályai

- A kiválasztott sémák objektumai teljes node-ként kerülnek a gráfba.
- Az objektumazonosító mindig tartalmazza az ownert.
- A kiválasztott sémák közötti kapcsolatok teljes értékű belső élek.
- Ha egy kiválasztott séma objektuma nem kiválasztott sémára hivatkozik, a cél `EXTERNAL_OBJECT` placeholderként megőrizhető.
- A placeholder ne kerüljön automatikusan a közösségdetektálásba, de a vizualizációban és külső kapcsolati mutatókban látható legyen.
- A `PUBLIC` synonymokat külön ownerként kell kezelni.
- Ugyanaz az objektumnév különböző sémákban vagy objektumtípusokban nem ütközhet.
- Quoted identifier esetén az eredeti case megőrzendő; normalizáláskor nem szabad két külön Oracle-nevet összevonni.

## 8. Oracle-metaadatok kinyerése

### 8.1. Alap objektumlista

Elsődleges forrás: `ALL_OBJECTS`, opcionális teljes katalógus-scope esetén `DBA_OBJECTS`.

```sql
SELECT owner, object_name, subobject_name, object_id,
       object_type, status, created, last_ddl_time
FROM all_objects
WHERE owner IN (:selected_owners)
ORDER BY owner, object_type, object_name
```

A tényleges implementáció dinamikusan generált bind placeholder-listát használjon. Az ismeretlen vagy ritka objektumtípusokat ne dobja el: `OTHER` logikai kategóriával és az eredeti Oracle object type megőrzésével tárolja.

### 8.2. Kinyerési mátrix

| Adat | Oracle-forrás | Node/él vagy metadata |
|---|---|---|
| Általános objektumok | `ALL_OBJECTS` | minden node alapadata |
| Programfüggőségek | `ALL_DEPENDENCIES` | `DEPENDS_ON` |
| Táblák | `ALL_TABLES` | TABLE metadata |
| Oszlopok | `ALL_TAB_COLUMNS` | alapból TABLE/VIEW metadata |
| Constraint-ek | `ALL_CONSTRAINTS` | PK/UK/check metadata és FK |
| Constraint-oszlopok | `ALL_CONS_COLUMNS` | FK forrás/cél oszloplista |
| View-k | `ALL_VIEWS` | definíció/hash és dependency-kiegészítés |
| Materialized view-k | `ALL_MVIEWS` | MV metadata |
| Indexek | `ALL_INDEXES` | INDEX node vagy technikai metadata |
| Indexoszlopok | `ALL_IND_COLUMNS` | index oszloplista |
| Triggerek | `ALL_TRIGGERS` | `TRIGGER_ON` + metadata |
| Synonymok | `ALL_SYNONYMS` | `POINTS_TO` vagy külső placeholder |
| PL/SQL forrás | `ALL_SOURCE` | opcionális statikus elemzés bemenete |
| Argumentumok | `ALL_ARGUMENTS` | procedure/function/package metadata |
| Sequence-ek | `ALL_SEQUENCES` | SEQUENCE node |
| Típusok | `ALL_TYPES`, `ALL_TYPE_ATTRS` | TYPE node és típuskapcsolat |
| Adatbázis-linkek | `ALL_DB_LINKS` | DB_LINK node, titok nélkül |
| Scheduler objektumok | `ALL_SCHEDULER_JOBS`, `ALL_SCHEDULER_PROGRAMS` | opcionális node és `RUNS` kapcsolat |
| DDL | `DBMS_METADATA.GET_DDL` | igény szerinti részlet, nem kötelező tömegesen |

### 8.3. Objektumfüggőségek

```sql
SELECT owner, name, type,
       referenced_owner, referenced_name, referenced_type,
       dependency_type, referenced_link_name
FROM all_dependencies
WHERE owner IN (:selected_owners)
  AND referenced_owner IS NOT NULL
```

- A source a függő objektum, a target a hivatkozott objektum.
- A `dependency_type` kerüljön az edge metadata mezőbe.
- A kiválasztott sémán kívüli target placeholderként maradjon meg.
- Az önhivatkozás a forrásgráfban megőrizhető, de az elemzési gráfból alapból ki kell szűrni.
- A package body függőségeit a logikai package node-hoz össze lehet vonni az elemzési nézetben.

### 8.4. Idegen kulcsok

Az FK-kat `ALL_CONSTRAINTS` és `ALL_CONS_COLUMNS` összekapcsolásával kell kinyerni. Összetett kulcsnál a `POSITION` alapján kell a forrás- és céloszlopokat párba rendezni.

Az él:

```text
source TABLE ── FOREIGN_KEY ──▶ target TABLE
```

Metadata:

```json
{
  "constraintName": "FK_ORDERS_CUSTOMER",
  "sourceColumns": ["CUSTOMER_ID"],
  "targetColumns": ["ID"],
  "deleteRule": "NO ACTION",
  "status": "ENABLED"
}
```

Az FK constraint ne legyen kötelezően önálló node; a közösségdetektálás számára ez torzító technikai csúcs lenne.

### 8.5. Triggerek, indexek és synonymok

- A trigger külön node, `TRIGGER_ON` éllel kapcsolódik a táblához vagy view-hoz; további dependencies az `ALL_DEPENDENCIES` alapján jönnek létre.
- Az index megjeleníthető külön node-ként, de az elemzési gráfban alapból a táblához tartozó technikai metadata legyen.
- A synonym külön node lehet a forrásgráfban. A `POINTS_TO` cél típusát névfeloldással kell meghatározni.
- Synonym láncnál maximális feloldási mélység szükséges, és ciklus esetén figyelmeztetés.
- DB linket használó synonym célja `EXTERNAL_OBJECT` legyen; távoli adatbázis automatikus bejárása nem része a tervnek.

### 8.6. Package spec és body

A forrásgráf megőrzi a `PACKAGE` és `PACKAGE BODY` Oracle-rekordokat és bizonyítékaikat. A logikai és elemzési gráfban egyetlen package node legyen, amelynek metadata mezői:

- specification status és last DDL time;
- body status és last DDL time;
- spec/body elérhetőség;
- összesített függőségek, az eredeti evidence megőrzésével.

### 8.7. Forráskód és dinamikus SQL

Az első használható verzió biztos kapcsolatai a katalógusnézetekből származnak. Opcionális második feldolgozási lépés vizsgálhatja az `ALL_SOURCE` és view definíciók statikus hivatkozásait:

- procedure/function/package hívások;
- `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE` objektumhivatkozások;
- sequence `NEXTVAL`/`CURRVAL` használat;
- statikusan felismerhető synonym-hivatkozások.

A dinamikus SQL-ben összefűzött nevek nem tekinthetők biztosnak. A rendszer különböztesse meg:

- `ORACLE_CATALOG`, confidence `1.0`;
- `STATIC_PARSER`, confidence tipikusan `0.8–0.95`;
- `HEURISTIC`, confidence a szabály alapján, legfeljebb `0.7`.

## 9. Normalizált gráfmodell

### 9.1. Stabil node-azonosító

```text
database_key::container_key::owner::normalized_object_type::object_name[::subobject]
```

Példa:

```text
local-oracle::ORCLPDB1::SALES::TABLE::ORDERS
```

Az Oracle `OBJECT_ID` attribútum, nem stabil alkalmazásazonosító, mert objektum-újralétrehozáskor megváltozhat.

### 9.2. Node szerződés

```json
{
  "id": "local-oracle::ORCLPDB1::SALES::TABLE::ORDERS",
  "owner": "SALES",
  "name": "ORDERS",
  "objectType": "TABLE",
  "oracleObjectType": "TABLE",
  "status": "VALID",
  "oracleObjectId": 123456,
  "createdAt": "2024-02-01T10:20:00Z",
  "lastDdlAt": "2026-07-01T08:15:00Z",
  "isExternal": false,
  "metadata": {}
}
```

### 9.3. Edge szerződés

```json
{
  "id": "rel-uuid",
  "source": "...::PACKAGE::ORDER_API",
  "target": "...::TABLE::ORDERS",
  "relationshipType": "DEPENDS_ON",
  "directed": true,
  "confidence": 1.0,
  "origin": "ORACLE_CATALOG",
  "metadata": {
    "dependencyType": "HARD"
  }
}
```

### 9.4. Kapcsolattípusok

| Kapcsolat | Jelentés |
|---|---|
| `DEPENDS_ON` | Oracle katalógusban ismert általános függőség |
| `FOREIGN_KEY` | táblák közötti referenciális kapcsolat |
| `TRIGGER_ON` | trigger eseményforrása |
| `INDEX_ON` | index és tábla technikai kapcsolata |
| `POINTS_TO` | synonym célja |
| `CONTAINS` | logikai tartalmazás, például package elem |
| `CALLS` | statikusan felismert programhívás |
| `READS_FROM` | statikusan felismert olvasás |
| `WRITES_TO` | statikusan felismert írás |
| `USES_SEQUENCE` | sequence használat |
| `RUNS` | scheduler job és program/eljárás kapcsolata |

## 10. Adatgyűjtési és publikálási pipeline

### 10.1. Állapotgép

```text
IDLE
  → CONNECTING
  → DISCOVERING_SCHEMAS
  → EXTRACTING_OBJECTS
  → EXTRACTING_RELATIONSHIPS
  → NORMALIZING
  → VALIDATING
  → PUBLISHING
  → SUCCEEDED

Bármely aktív állapot → FAILED vagy CANCELLED
```

### 10.2. Feldolgozási lépések

1. A konfiguráció és a kiválasztott sémák validálása.
2. Oracle-kapcsolat és capabilities ellenőrzése.
3. Új `.next.db` létrehozása és SQLite-séma inicializálása.
4. Objektumok streamelt kinyerése batch insert segítségével.
5. Típusfüggő részletek és kapcsolatok kinyerése.
6. Stabil ID-k képzése és target node-ok feloldása.
7. Külső placeholder node-ok létrehozása.
8. Evidence és confidence rögzítése.
9. Duplikált katalógusrekordok normalizálása, az eltérő bizonyítékok megőrzésével.
10. Integritás- és lefedettség-ellenőrzés.
11. SQLite indexek létrehozása és `ANALYZE` futtatása.
12. Atomikus publikálás az aktuális fájl helyére.
13. Az alapértelmezett elemzés kézi vagy opcionális automatikus indítása.

### 10.3. Integritásellenőrzések

- minden nem külső edge-végpont létezzen;
- ne legyen két eltérő objektum azonos stabil ID-val;
- FK összetett oszloppozíciói legyenek folytonosak;
- package spec/body összevonása ne veszítsen evidence-et;
- ismeretlen referenced object placeholderként jelenjen meg;
- node- és edge-számlálók egyezzenek a betöltött rekordokkal;
- a kiválasztott sémák mindegyike szerepeljen a lefedettségi riportban;
- SQLite `PRAGMA integrity_check` eredménye `ok` legyen.

### 10.4. Lefedettségi riport

A scan után jelenjen meg:

- objektumszám owner és típus szerint;
- kapcsolatszám típus, origin és confidence szerint;
- külső placeholder node-ok száma;
- fel nem oldott synonymok száma;
- hiányzó nézetjogok;
- figyelmen kívül hagyott vagy ismeretlen Oracle objektumtípusok;
- parserhibák és heurisztikus találatok;
- teljes futási idő fázisonként.

## 11. A három gráfréteg

### 11.1. Forrásgráf

A forrásgráf az Oracle-ből kinyert tények lehető legteljesebb reprezentációja:

- irányított;
- párhuzamos éleket is tartalmazhat;
- technikai objektumokat is megőriz;
- minden kapcsolatnál origin, confidence és evidence szerepel;
- nem módosul az elemzési beállítások hatására.

### 11.2. Elemzési gráf

Az elemzési gráf a kiválasztott analysis runhoz előállított származtatott gráf:

- objektumtípus és owner szerint szűrt;
- technikai node-okat összevonhat vagy kizárhat;
- önhurkok nélkül;
- párhuzamos élekből egyetlen súlyozott kapcsolatot képez;
- confidence-del korrigált;
- hubkezelést alkalmazhat;
- a közösségdetektáláshoz alapból irányítatlanná válik.

### 11.3. Megjelenítési gráf

A megjelenítési gráf mindig a felhasználói kérdéshez igazított részhalmaz:

- objektum környezete adott mélységig;
- közösség teljes vagy mintavett belső gráfja;
- közösségekre összecsukott aggregált gráf;
- útvonal vagy hatáselemzés eredménye;
- szűrt objektumtípusok és kapcsolatok.

A teljes több tízezres gráf egyben történő kirajzolása nem elsődleges használati mód.

## 12. Elemzési gráf előállítása

### 12.1. Feldolgozási pipeline

```text
aktuális forrásgráf
  → owner- és objektumtípus-szűrés
  → külső placeholder policy
  → package spec/body összevonás
  → technikai node policy
  → önhurkok eltávolítása
  → párhuzamos élek aggregálása
  → confidence alkalmazása
  → kapcsolattípus-súlyozás
  → hubkorrekció
  → irányok szimmetrizálása
  → komponensek kezelése
  → igraph gráf létrehozása
```

Minden analysis run tárolja a pipeline teljes konfigurációját és számlálóit: hány node/él került be, esett ki, egyesült vagy kapott korrigált súlyt.

### 12.2. Elemzésbe kerülő objektumok

Alapértelmezett logikai objektumok:

- TABLE;
- VIEW;
- MATERIALIZED VIEW;
- PACKAGE;
- PROCEDURE;
- FUNCTION;
- TRIGGER;
- TYPE.

Alapból kizárt vagy összevont technikai objektumok:

- INDEX;
- constraint;
- partíció;
- LOB és belső rendszerobjektum;
- package body külön node-ja;
- synonym, ha csak alias és nem hordoz külön jelentést;
- EXTERNAL_OBJECT a közösségdetektálásban.

A felület adjon „technikai objektumok bevonása” kapcsolót, de figyelmeztesse a felhasználót a torzítás veszélyére.

### 12.3. Kezdő súlyprofil

| Kapcsolat | Alapsúly | Indoklás |
|---|---:|---|
| `FOREIGN_KEY` | 5.0 | erős adatmodell-kapcsolat |
| biztos view dependency / `READS_FROM` | 4.0 | erős logikai adatfüggés |
| `TRIGGER_ON` | 4.0 | szoros életciklus-kapcsolat |
| `WRITES_TO` | 4.0 | erős működési csatolás |
| `DEPENDS_ON` | 3.0 | általános statikus függőség |
| `CALLS` | 3.0 | programozott kapcsolat |
| `READS_FROM` parserből | 3.0 | confidence-del korrigálva |
| `CONTAINS` | 2.0 | logikai tartalmazás |
| `USES_SEQUENCE` | 1.5 | adat-előállítási kapcsolat |
| `POINTS_TO` | 1.0 | alias jellegű kapcsolat |
| `INDEX_ON` | 0.5 | technikai kapcsolat, általában kizárva |

Egy él elemzési súlya:

```text
effective_weight = base_weight × confidence × hub_factor
```

### 12.4. Párhuzamos élek aggregálása

A forrásgráf minden kapcsolatot megőriz. Az elemzési gráfban az azonos node-pár közötti kapcsolatok ajánlott aggregálása:

1. kapcsolattípusonként a legnagyobb effective weight kiválasztása;
2. a típusonkénti értékek összeadása;
3. felső korlát alkalmazása, alapból `10.0`.

```text
w(A,B) = min(10, Σ max(weight per relationship type))
```

Így több különböző szemantikai kapcsolat erősíti az összetartozást, de sok azonos dependency rekord nem dominál korlátlanul.

### 12.5. Irányok kezelése

A forrásgráf irányított marad. A közösségdetektálási gráf alapértelmezett szimmetrizálása:

```text
w_undirected(A,B) = min(10, w(A→B) + w(B→A))
```

A hatás-, PageRank- és hívási elemzés továbbra is az irányított gráfot használja.

### 12.6. Hubkezelés

Az olyan közös objektumok, mint `COMMON_UTILS`, `CURRENCIES`, `CONFIGURATION` vagy `AUDIT_LOG`, mesterségesen összeránthatják a közösségeket.

Három választható policy:

1. **NONE:** nincs korrekció, kontrollfutás.
2. **DEGREE_NORMALIZATION:**

```text
hub_factor(A,B) = 1 / sqrt(log(2 + degree(A)) × log(2 + degree(B)))
```

3. **EXCLUDE_TOP_HUBS:** a fokszám szerinti felső 1% ideiglenes kizárása a klaszterezésből; az objektumok később `SHARED_INFRASTRUCTURE` jelölést kapnak.

Az alapértelmezett profil `DEGREE_NORMALIZATION`. Minden eredmény mutassa meg, mely node-okra volt lényeges hatása a korrekciónak.

### 12.7. Izolált node-ok és komponensek

- Fokszám nélküli node: `ISOLATED`, ne kapjon mesterséges üzleti közösséget.
- Két-három node-os külön komponens: maradhat önálló kis közösség, de `SMALL_COMPONENT` figyelmeztetéssel.
- A Leiden algoritmus connected componentenként fusson, majd globálisan egyedi közösségazonosítók készüljenek.
- Az alapértelmezett minimális közösségméret `3`; kisebb eredmények külön listán jelenjenek meg.

## 13. Közösségdetektálás

### 13.1. Elsődleges algoritmus: Leiden

A Leiden algoritmus illeszkedik a célhoz: olyan csoportokat keres, amelyekben sok a belső és kevés a külső kapcsolat. Súlyozott gráfot kezel, nem igényli a közösségek számának előzetes megadását, és nagyobb gráfokon is használható.

Tárolandó paraméterek:

- objective: `CPM` vagy `MODULARITY`;
- resolution;
- seed;
- iterációszám;
- súlyprofil;
- hub policy;
- objektum- és kapcsolattípus-szűrők;
- minimum confidence;
- technikai node policy;
- alkalmazás- és igraph-verzió.

Alapértelmezett futás:

```text
algorithm: Leiden
objective: CPM
resolution: 1.0
seed: 42
iterations: until stable / könyvtár által támogatott negatív érték
hub policy: DEGREE_NORMALIZATION
minimum confidence: 0.8
minimum community size: 3
```

### 13.2. Resolution-vizsgálat

Az alkalmazás kínáljon gyors előre definiált sorozatot:

```text
0.1, 0.2, 0.5, 1.0, 2.0, 5.0
```

- kisebb resolution: kevesebb, nagyobb közösség;
- nagyobb resolution: több, kisebb közösség.

Minden értéknél számítandó:

- közösségek száma;
- közösségméret-eloszlás;
- singleton és small component arány;
- quality/modularity;
- belső súly aránya;
- átlagos és medián conductance;
- sématisztaság;
- futási idő.

A felület a sorozat eredményeit táblázatban és egyszerű görbéken hasonlítsa össze. A felhasználó az érdekes futást aktiválhatja a gráfnézethez.

### 13.3. Stabilitás több seeddel

Egy kiválasztott konfiguráció opcionálisan fusson például `5` seeddel. Összehasonlítás:

- Adjusted Rand Index;
- Normalized Mutual Information;
- Variation of Information;
- node-szintű stabilitás: a fő szomszédokkal való együttklaszterezés gyakorisága.

Az alkalmazás a közösséget `STABLE`, `MIXED` vagy `UNSTABLE` jelzővel lássa el konfigurálható, de dokumentált küszöbök alapján. Az alapértelmezett egyetlen seed a gyors interaktív használatot szolgálja; a többseedes futás külön gomb legyen.

### 13.4. Kontrollalgoritmusok

Az első implementáció kötelező algoritmusa Leiden. Az elemző interfész azonban közös absztrakciót használjon, hogy később könnyen hozzáadható legyen:

- Louvain gyors kontrollként;
- Infomap, ha az információ- vagy függőségáramlás értelmezése fontos;
- Label Propagation nagyon nagy gráf gyors becsléséhez;
- Weakly Connected Components szerkezeti alapfelosztásként.

Ezek ne növeljék az első verzió UI-ját vagy függőségeit; csak az algoritmusmodul interfésze legyen bővíthető.

## 14. Közösség- és gráfminőségi mutatók

### 14.1. Közösségenkénti mutatók

- node-ok száma;
- belső és külső élek száma;
- belső és külső kapcsolati súly;
- internal density;
- external ratio;
- conductance;
- coverage;
- owner/schema eloszlás;
- objektumtípus-eloszlás;
- top belső hubok;
- top kimenő bridge objektumok;
- kapcsolattípus-eloszlás;
- stabilitási jelző;
- minőségi figyelmeztetések.

Definíciók:

```text
internal_density = belső élek / lehetséges belső élek

external_ratio = külső élsúly / (belső élsúly + külső élsúly)

conductance = külső élsúly /
              min(közösség súlyozott volumene,
                  gráf többi részének súlyozott volumene)
```

Az alacsony conductance és external ratio, illetve a magas belső súly jellemzően jobban elkülönülő közösséget jelez.

### 14.2. Teljes particionálás mutatói

- Leiden quality vagy modularity;
- teljes belső élsúly aránya;
- közösségek száma és méreteloszlása;
- izolált node-ok aránya;
- hubok közösségközi kapcsolati súlya;
- schema és community egyezésének mértéke;
- futási idő és becsült peak memory.

### 14.3. Sématisztaság

A schema ne legyen kötelező közösséghatár. Minden közösséghez számítandó:

```json
{
  "schemaDistribution": {
    "SALES": 18,
    "COMMON": 4,
    "REPORTING": 2
  },
  "dominantSchema": "SALES",
  "dominantSchemaRatio": 0.75
}
```

Külön összesítés mutassa meg:

- egy séma hány közösségre oszlik;
- egy közösség hány sémát metsz;
- mely sémák között a legerősebb a kapcsolati súly;
- mely közösségek lépik át leginkább a sémahatárokat.

## 15. Központiság, bridge-ek és egyéb elemzések

### 15.1. Weighted degree / strength

Gyors, könnyen magyarázható mutató. Külön számítandó:

- teljes strength;
- belső közösségi strength;
- külső közösségi strength;
- in-degree és out-degree az irányított forrásgráfon.

A magas külső/belső arányú objektum valószínű bridge vagy megosztott infrastruktúra.

### 15.2. PageRank

Az irányított forrásgráfon használható a globálisan fontos, sok jelentős objektum által hivatkozott node-ok rangsorolására. Kapcsolattípus-súlyok alkalmazhatók. A damping alapértéke `0.85`.

### 15.3. Betweenness centrality

Azonosítja azokat az objektumokat, amelyek sok legrövidebb útvonalon helyezkednek el. Nagy gráfon a pontos számítás drága, ezért:

- 20 000 node alatt pontos számítás engedhető;
- fölötte mintavételes/approximált számítás legyen;
- a mintaméret kerüljön az eredmény konfigurációjába.

### 15.4. Articulation point és bridge edge

Az irányítatlan elemzési gráfon keresse azokat a node-okat és éleket, amelyek eltávolítása komponensekre bontaná a gráfot. Ezek lehetséges architekturális szűk keresztmetszetek.

### 15.5. K-core

A k-core elemzés mutassa meg a sűrűn összekapcsolt magokat. Közösségenként is számítható, hogy elkülönüljön a csoport stabil magja és perifériája.

## 16. Hatáselemzés és útvonalkeresés

### 16.1. Hatáselemzés

Két mód:

- **Dependents:** mi függ közvetlenül vagy közvetve ettől az objektumtól?
- **Dependencies:** mitől függ közvetlenül vagy közvetve ez az objektum?

Paraméterek:

- maximum depth, alapból `5`;
- engedélyezett kapcsolattípusok;
- minimum confidence;
- bejövő/kimenő/mindkét irány;
- maximum node és edge;
- technikai node-ok megjelenítése;
- közösséghatár elérésekor vizuális jelzés.

A bejárás BFS alapú, ciklusbiztos és meglátogatott node-onként tárolja a minimális mélységet. A felület egyértelműen jelezze, hogy ez statikus metaadat alapján becsült, lehetséges hatás.

### 16.2. Útvonalkeresés

Támogatandó módok:

- legrövidebb út hopszám alapján;
- legrelevánsabb út súlyozott költséggel;
- legfeljebb `k=3` alternatív út;
- irányított vagy irányítatlan keresés.

Szemantikai költség:

```text
edge_cost = 1 / effective_weight
```

Az útvonal minden lépésénél látszódjon a kapcsolattípus, irány, súly, confidence és evidence.

## 17. Közösségek értelmezése és elnevezése

### 17.1. Automatikus névjavaslat

A Leiden csak számozott közösségeket ad. A helyi névjavaslat használja:

- domináns sémát;
- objektumnevek leggyakoribb tokenjeit/prefixeit;
- legközpontibb TABLE és PACKAGE objektumokat;
- objektumtípus-eloszlást;
- stopword-listát, például `PKG`, `API`, `TBL`, `VIEW`, `PROC`.

Példa:

```text
SALES / ORDER – központi objektum: SALES.ORDERS
```

A névjavaslat magyarázata jelenjen meg. A felhasználó kézzel felülírhatja és megjegyzést adhat hozzá. A kézi címke csak az aktuális adathalmazban él.

### 17.2. Közösség összecsukása

A közösségi gráfban minden közösség egy node:

```text
[Sales / Order: 42 objektum]
          │ 7 kapcsolat, súly 19.5
          ▼
[Billing: 25 objektum]
```

Az aggregált közösségi él tárolja:

- a két közösség közötti élek számát;
- teljes és irányonkénti súlyt;
- kapcsolattípus-eloszlást;
- top bridge objektumpárokat.

### 17.3. Hierarchikus elemzés

Opcionális, de a terv része:

1. alacsony resolution értékkel nagy közösségek keresése;
2. a minimum méretnél nagyobb közösségek rekurzív újraelemzése;
3. szülő–gyermek közösségstruktúra kialakítása;
4. ugyanazon súlyprofil és hub policy használata, de közösségenként külön resolution engedélyezése.

A hierarchia kísérleti funkció legyen, mert a különböző resolution eredmények nem mindig alkotnak tiszta fát.

## 18. Backend API

### 18.1. Alapelvek

- REST + JSON;
- nincs auth és user context;
- hosszú műveletek `202 Accepted` válasszal indulnak;
- egyszerre egy aktív hosszú művelet;
- egységes hibaforma `code`, `message`, `details` mezőkkel;
- minden részgráf-lekérdezés szerveroldali limittel működik.

### 18.2. Endpointok

```text
GET    /api/config
GET    /api/connection/capabilities
POST   /api/connection/test

POST   /api/scan
GET    /api/scan/status
POST   /api/scan/cancel
GET    /api/scan/statistics

GET    /api/objects
GET    /api/objects/{objectId}
GET    /api/objects/{objectId}/neighbors
POST   /api/subgraph
POST   /api/paths
POST   /api/impact

POST   /api/analyses
GET    /api/analyses
GET    /api/analyses/{analysisId}
POST   /api/analyses/{analysisId}/cancel
DELETE /api/analyses/{analysisId}
GET    /api/analyses/{analysisId}/communities
GET    /api/analyses/{analysisId}/communities/{communityId}
GET    /api/analyses/{analysisId}/community-graph
POST   /api/analyses/compare

POST   /api/annotations
PATCH  /api/annotations/{annotationId}
POST   /api/export
GET    /api/export/{exportId}/status
GET    /api/export/{exportId}/file
```

### 18.3. Scan kérés

```json
{
  "schemas": ["SALES", "BILLING", "COMMON"],
  "objectTypes": [],
  "includeSourceCode": false,
  "resolveExternalReferences": true,
  "includeSchedulerObjects": false
}
```

Az üres `objectTypes` minden látható objektumot jelent. A támogatott logikai típusok részletes metadata-extractort kapnak; a többi generikus node-ként megmarad.

### 18.4. Elemzési kérés

```json
{
  "name": "Leiden – normalizált hubok",
  "algorithm": "LEIDEN",
  "objective": "CPM",
  "resolution": 1.0,
  "seed": 42,
  "objectTypes": [
    "TABLE", "VIEW", "MATERIALIZED_VIEW", "PACKAGE",
    "PROCEDURE", "FUNCTION", "TRIGGER", "TYPE"
  ],
  "owners": ["SALES", "BILLING", "COMMON"],
  "minimumConfidence": 0.8,
  "minimumCommunitySize": 3,
  "edgeWeights": {
    "FOREIGN_KEY": 5.0,
    "DEPENDS_ON": 3.0,
    "TRIGGER_ON": 4.0,
    "POINTS_TO": 1.0
  },
  "parallelEdgeAggregation": "TYPE_MAX_THEN_CAPPED_SUM",
  "parallelEdgeWeightCap": 10.0,
  "hubPolicy": "DEGREE_NORMALIZATION",
  "directionPolicy": "SYMMETRIZE_SUM",
  "includeTechnicalObjects": false
}
```

### 18.5. Részgráf-limitek

- maximum depth: `3` interaktív részgráfnál;
- alap maximum: `500` node és `2 000` él;
- hard maximum: `2 000` node és `10 000` él;
- limit elérésekor `truncated: true` és szűkítési javaslat;
- nagyobb eredmény csak exportként készülhessen el.

## 19. Frontend és UX

### 19.1. Képernyők

1. **Kapcsolat és adatgyűjtés:** connection test, elérhető sémák, kiválasztás, scan progress.
2. **Áttekintő:** objektum- és kapcsolatszámok, schema/type eloszlás, lefedettségi figyelmeztetések.
3. **Objektumkereső:** név, owner, típus, státusz és wildcard szűrés.
4. **Gráfböngésző:** részgráf, irány, depth, kapcsolattípus és confidence szűrők.
5. **Objektumrészlet:** metadata, DDL/forrás ha elérhető, kapcsolatok és evidence.
6. **Közösségelemzés:** paraméterezés, állapot, futások és mutatók összehasonlítása.
7. **Közösségi térkép:** összecsukott nézet, drill-down, bridge objektumok.
8. **Hatáselemzés és útvonal:** célzott kétlépcsős munkafolyamat.
9. **Export:** aktuális nézet vagy teljes elemzési eredmény.

### 19.2. Gráfinterakciók

- node-ra kattintás: detail panel;
- szomszédok betöltése bejövő, kimenő vagy mindkét irányban;
- node rögzítése és lokális elrendezés újrafuttatása;
- közösség szerinti színezés;
- objektumtípus szerinti alak vagy ikon;
- `INVALID` objektum külön kerettel/jelöléssel;
- bizonytalan él szaggatott vonallal;
- edge-re kattintva evidence és metadata;
- közösség izolálása, összecsukása vagy kibontása;
- „Miért került ide?” panel top belső élekkel és külső kapcsolati aránnyal.

### 19.3. Elrendezések

- kisebb általános gráf: fCoSE vagy CoSE;
- függőségi irány: dagre/ELK;
- közösségi aggregált gráf: fCoSE;
- nagyobb eredmény: szerveroldalon korlátozott részgráf és opcionálisan cache-elt preset pozíciók.

A layout ne fusson újra minden kisebb stílusváltoztatásnál. A felhasználó külön gombbal indíthassa újra.

### 19.4. Elemzőt segítő UX

- alapértelmezett súlyprofil és rövid magyarázat minden paraméterhez;
- resolution presetek egy kattintással;
- az elemzési futások egymás melletti összehasonlítása;
- legjobb és legrosszabb conductance-ű közösségek gyors listája;
- top hubok és bridge-ek külön rangsora;
- schema–community mátrix;
- minden táblázatból közvetlen ugrás a gráfhoz;
- a paraméterek és eredmények exportálása együtt.

## 20. Export

Támogatandó formátumok:

- JSON: nodes, edges, analysis config, memberships és metrics;
- CSV: objektumok, kapcsolatok, közösségtagság, közösségmutatók és centralitás külön fájlokban;
- SVG/PNG: aktuális vizuális nézet;
- opcionális GraphML a külső gráfeszközök számára.

Az export legyen determinisztikus sorrendű, hogy két manuálisan archivált futás fájlszinten is könnyebben összevethető legyen. Az Oracle-jelszó és connect string érzékeny részei soha ne kerüljenek exportba.

## 21. Teljesítmény és memória

### 21.1. Méretkategóriák

| Kategória | Node | Nyers él | Megközelítés |
|---|---:|---:|---|
| Kicsi | <10k | <100k | teljes memóriás elemzés |
| Közepes | 10k–100k | 100k–1M | streamelt scan, memóriás igraph |
| Nagy | 100k–500k | 1M–5M | komponensenkénti elemzés, approximált centralitás |
| Ennél nagyobb | >500k | >5M | külön benchmark és szigorúbb szűrés szükséges |

### 21.2. Optimalizálási sorrend

1. Oracle-lekérdezések csak szükséges oszlopokkal és owner filterrel.
2. `arraysize` és `prefetchrows` méréssel beállítva.
3. SQLite batch insert tranzakciónként több ezer rekorddal.
4. Indexek csak a tömeges betöltés után.
5. Elemzés előtt egyetlen rendezett edge-lista betöltése.
6. Technikai objektumok kizárása a közösségdetektálásból.
7. Connected componentenkénti futtatás.
8. Betweenness approximáció nagy gráfon.
9. Frontenden részgráf és közösség-összecsukás.

### 21.3. Erőforráskorlátok

- maximális scan futási idő konfigurálható, alapból 60 perc;
- elemzés maximum node/edge limitje konfigurálható;
- hard UI-limitek a részgráfokra;
- memóriahiány esetén az elemzés kontrollált hibával álljon le, az SQLite-adat ne sérüljön;
- a frontend jelezze az elemzési gráf becsült méretét indítás előtt.

## 22. Hibakezelés

### 22.1. Oracle-hibák

- hibás hitelesítés: rövid, érthető üzenet és Oracle hibakód;
- hiányzó nézetjog: részleges capabilities és konkrét hiányzó nézet;
- kapcsolat megszakadása: scan `FAILED`, előző adathalmaz változatlan;
- egy extractor nem kritikus hibája: konfiguráció szerint teljes scan hiba vagy warning; alapból a fő objektum/dependency/FK extractor hibája kritikus;
- timeout: aktuális query és fázis jelzése érzékeny bind értékek nélkül.

### 22.2. Elemzési hibák

- üres elemzési gráf: paraméterezési magyarázat;
- csak izolált node-ok: nincs Leiden-futtatás, külön lista;
- negatív/null súly: konfigurációvalidációs hiba;
- túl nagy gráf: szűkítési javaslat;
- numerikus centralitási hiba: az adott mutató hibás, a többi eredmény megmaradhat;
- megszakítás: részleges membership ne váljon sikeres analysis runná.

### 22.3. Helyi naplózás

Egyszerű konzol- és forgó fájllog elegendő. Tartalmazza:

- időpont, szint, művelet és fázis;
- futási idő és számlálók;
- Oracle hibakód;
- elemzés paraméterazonosítója.

Ne tartalmazzon jelszót, teljes connect descriptort vagy PL/SQL forrást.

## 23. Tesztelési stratégia

### 23.1. Unit tesztek

- stabil ID és quoted identifier;
- objektumtípus-normalizálás;
- package spec/body összevonás;
- edge evidence és confidence;
- párhuzamos él aggregáció és súlycap;
- hubkorrekció;
- conductance, density és external ratio;
- BFS hatáselemzés és cikluskezelés;
- útvonalköltség;
- közösségnév tokenizálása.

### 23.2. Oracle integration tesztek

Golden séma tartalmazzon:

- legalább három sémát;
- azonos nevű táblát két sémában;
- sémák közötti FK-t;
- package spec/body-t;
- procedure/function hívást;
- view és materialized view dependency-t;
- triggert;
- indexet és összetett FK-t;
- local és PUBLIC synonymot;
- synonym láncot és ciklust;
- sequence-használatot;
- külső sémára hivatkozást;
- invalid objektumot;
- quoted mixed-case objektumot.

### 23.3. Gráfalgoritmus-regresszió

Rögzített tesztgráfok:

- két erős közösség egy bridge-dzsel;
- három közösség közös hubbal;
- izolált node-ok;
- párhuzamos és többtípusú élek;
- irányított ciklus;
- több disconnected component;
- egy nagy, gyenge belső szerkezetű közösség;
- schema-határokat átlépő közösség.

Fix input + konfiguráció + seed esetén ellenőrizendő a membership, quality és fő közösségmutatók. Könyvtárfrissítéskor a változást tudatosan kell felülvizsgálni.

### 23.4. SQLite és újrafuttatási tesztek

- üres adatfájl inicializálása;
- nagy batch insert;
- indexek létrehozása;
- `.next.db` sikeres promóciója;
- Oracle-hiba közben a régi fájl megmaradása;
- megszakítás közben a régi fájl megmaradása;
- új scan után a korábbi analysis runok eltűnése;
- `integrity_check` hibánál nincs publikálás.

### 23.5. API és frontend tesztek

- kapcsolatpróba és sémalista;
- scan indítás, státusz, cancel és hiba;
- keresés owner/type/name szerint;
- részgráf-limit és truncation;
- elemzésindítás és paramétervalidáció;
- közösségi drill-down;
- impact és path eredmény;
- export;
- Docker Compose indulás tiszta `data/` könyvtárral.

### 23.6. Felhasználói elfogadási próba

Az elemző egy reprezentatív adatbázison:

1. önállóan elindítja az alkalmazást;
2. kiválaszt legalább három sémát;
3. ellenőriz kézzel 50 objektumot és 100 kapcsolatot;
4. lefuttat legalább három resolution-profilt;
5. értelmez legalább tíz közösséget;
6. azonosít hubokat és bridge objektumokat;
7. lefuttat egy hatás- és egy útvonalelemzést;
8. exportálja a végső eredményt.

## 24. Megvalósítási ütemterv

### 0. fázis – Technikai felmérés (1 hét)

- Oracle-verzió, PDB, kiválasztandó sémák és adatmennyiség felmérése.
- Read-only felhasználó és `ALL_*` hozzáférés ellenőrzése.
- Thin mód kapcsolatpróba.
- Objektum- és kapcsolatszám becslése.
- Kis reprezentatív kivonat és igraph memória-benchmark.

**Eredmény:** végleges támogatási mátrix és mért célméret.

### 1. fázis – Alkalmazásváz és SQLite (1 hét)

- monorepo;
- Dockerfile és Docker Compose;
- FastAPI + buildelt React kiszolgálás;
- `.env` konfiguráció;
- SQLite-séma és repository réteg;
- in-process task állapotgép.

**Demo:** alkalmazás egy paranccsal indul, kapcsolatpróba működik.

### 2. fázis – Többsémás Oracle scanner (2 hét)

- capabilities és sémaválasztás;
- objektum-, dependency-, FK-, trigger-, index- és synonym-extractor;
- stabil ID, placeholder és evidence;
- package spec/body összevonás;
- atomikus `.next.db` publikálás;
- lefedettségi riport.

**Demo:** több séma közös, konzisztens forrásgráfja.

### 3. fázis – Gráf API és böngésző (2 hét)

- objektumkeresés és facetták;
- neighbor/subgraph API;
- Cytoscape gráfnézet;
- objektum- és edge-detail/evidence;
- hatáselemzés és útvonalkeresés;
- limit- és hibakezelés.

**Demo:** keresésből induló interaktív gráffeltárás.

### 4. fázis – Elemzési pipeline (2 hét)

- technikai node policy;
- súlyozás, confidence, edge aggregation;
- hubkezelés és szimmetrizálás;
- Leiden és resolution-sorozat;
- közösségmutatók;
- centralitás, bridge, articulation point és k-core.

**Demo:** összehasonlítható, magyarázható közösségi eredmények.

### 5. fázis – Elemzői felület és validáció (1–2 hét)

- közösségi aggregált gráf;
- paraméter- és futás-összehasonlítás;
- schema–community nézet;
- névjavaslat és annotation;
- JSON/CSV/SVG/PNG export;
- teljesítményhangolás;
- golden séma, algoritmusregresszió és felhasználói próba;
- README és rövid használati útmutató.

**Eredmény:** felmérésre kész, helyben futó alkalmazás.

## 25. Elfogadási kritériumok

### Adatgyűjtés

- Egy Oracle-adatbázis több kiválasztott sémája egy futásban feldolgozható.
- Azonos nevű, eltérő ownerű objektumok nem ütköznek.
- Sémák közötti dependencies és FK-k megmaradnak.
- Sikertelen új scan nem sérti az előző sikeres adatfájlt.
- Sikeres új scan teljesen lecseréli a korábbi felmérést.
- A scan lefedettségi riportot készít.

### Gráf és elemzés

- A raw, analysis és view graph fogalma az implementációban külön réteg.
- A súly-, confidence-, edge aggregation- és hub policy konfigurálható és mentett.
- A Leiden fix seed mellett reprodukálható.
- Több resolution eredménye összehasonlítható.
- Minden közösséghez rendelkezésre áll conductance, density, belső/külső súly, schema- és típuseloszlás.
- Elérhető a weighted degree, PageRank, bridge és megfelelő méretig betweenness.
- Hatás- és útvonalelemzés ciklusbiztos és limitált.

### Felhasználói élmény

- Az alkalmazás egy Docker Compose paranccsal indul.
- Nincs bejelentkezés vagy adminisztráció.
- A felhasználó a böngészőből tud sémát választani, scant és elemzést indítani.
- A hosszú műveletek állapota és hibája látható.
- A gráf kereshető, szűrhető, bővíthető és közösségekre összecsukható.
- Az eredmények a paraméterekkel együtt exportálhatók.

## 26. Kockázatok és mérséklés

| Kockázat | Következmény | Mérséklés |
|---|---|---|
| Hiányos Oracle katalógusjog | hiányos gráf | capabilities és lefedettségi riport |
| Dinamikus SQL nem látható | hiányzó kapcsolatok | confidence/origin, opcionális parser, korlát jelzése |
| Technikai objektumok torzítanak | félrevezető közösségek | alapértelmezett kizárás/összevonás |
| Közös hubok összerántják a modulokat | túl nagy közösségek | hubnormalizálás és kontrollfutás |
| Resolution önkényes | instabil felosztás | preset sorozat, több seed és mutatók |
| Nagy gráf memóriaigénye | sikertelen elemzés | komponensek, szűrés, approximáció, előzetes becslés |
| Egyetlen SQLite-fájl sérülése | eredményvesztés | `.next.db`, integrity check és atomikus csere |
| Közösség tévesen üzleti modulnak tűnik | rossz következtetés | magyarázható mutatók és emberi értelmezés |
| Synonym/DB link nem oldható fel | hiányos célkapcsolat | placeholder node és warning |
| Dockerből nem érhető el Oracle | alkalmazás használhatatlan | connection test, hálózati dokumentáció, szükség esetén host gateway |

## 27. Első konkrét lépések

1. Kijelölni a felmérendő Oracle-adatbázist és legalább három reprezentatív sémát.
2. Lekérni az Oracle-verziót, PDB/container nevet és a becsült objektumszámokat.
3. Létrehozni vagy ellenőrizni a read-only metadata felhasználót.
4. Kipróbálni a `python-oracledb` Thin kapcsolatot Docker konténerből.
5. Futtatni a fő `ALL_OBJECTS`, `ALL_DEPENDENCIES` és FK lekérdezéseket.
6. Létrehozni a golden tesztsémát több ownerrel.
7. Benchmarkolni egy reprezentatív node/edge kivonatot igraph/Leiden alatt.
8. Rögzíteni az alapértelmezett objektumtípus- és súlyprofilt.
9. Implementálni az atomikus SQLite-cserét még a teljes scanner előtt.
10. Az első valós eredményen doménszakértővel kalibrálni a súlyokat és hub policy-t.

## 28. Hivatalos technikai hivatkozások

- [Oracle – schema object dictionary views](https://docs.oracle.com/en/database/oracle/oracle-database/26/admin/managing-schema-objects.html)
- [Oracle – DBMS_METADATA használata](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/using-oracle-dbms_metadata-api.html)
- [python-oracledb – Thin és Thick mód inicializálása](https://python-oracledb.readthedocs.io/en/stable/user_guide/initialization.html)
- [python-igraph – Graph API és Leiden](https://igraph.org/python/versions/latest/api/igraph.Graph.html)
- [leidenalg – resolution profile](https://leidenalg.readthedocs.io/en/latest/reference.html)
- [Cytoscape.js – hivatalos dokumentáció](https://js.cytoscape.org/)

## 29. Összegzés

A megoldás szándékosan egyszerű futtatási és tárolási modellt használ: egy Docker Compose szolgáltatás, egy FastAPI backend, egy React frontend és egyetlen SQLite-fájl. Ez elhagyja a többfelhasználós és vállalati üzemeltetési rétegeket, de nem egyszerűsíti le a felmérés szakmai magját.

A rendszer értékét a megbízható több-sémás Oracle-kinyerés, a bizonyítékokkal ellátott forrásgráf, a konfigurálható elemzési gráf és a magyarázható közösségdetektálás együtt adja. Az alkalmazás akkor tekinthető sikeresnek, ha az elemző nemcsak egy látványos hálózatot kap, hanem meg tudja válaszolni: mely objektumok tartoznak szorosan össze, miért kerültek egy csoportba, mennyire különülnek el, mely elemek kötik össze a csoportokat, és milyen függőségi következményekkel járhat egy objektum módosítása.
