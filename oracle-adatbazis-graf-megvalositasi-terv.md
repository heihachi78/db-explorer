# Oracle adatbázis-objektumgráf és elemzőalkalmazás – részletes megvalósítási terv

**Dokumentum állapota:** megvalósítás alatt álló, karcsúsított terv

**Dátum:** 2026-07-15

**Cél:** egyszeri, egyfelhasználós Oracle-adatbázis-felmérés támogatása

**Scope-elv:** csak olyan funkció része a tervnek, amely közvetlenül javítja a
kinyerés helyességét, az elemzés használhatóságát vagy az egyetlen helyi
adatfájl biztonságát. Többfelhasználós működés, tartós szolgáltatásüzemeltetés,
auditálás, automatikus ütemezés és általános célú bővíthetőség nem követelmény.

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

### 2.2. Gyakorlati sikerkritériumok

- Az Oracle-kapcsolat kizárólag olvasási célú; az alkalmazás nem módosítja a
  forrásadatbázist.
- Azonos nevű, eltérő ownerű vagy típusú objektumok nem ütköznek.
- A látható katalógusadatokból származó, támogatott objektumok és kapcsolatok
  megmaradnak, a kimaradások pedig a lefedettségi riportban látszanak.
- Azonos adat, konfiguráció és seed azonos elemzési eredményt ad.
- A keresés és a korlátozott részgráf-bejárás a céladatbázis tipikus
  használatában interaktív marad; ehhez nincs általános SLA.
- Az alkalmazás egyetlen `docker compose up --build` paranccsal indítható.
- Egy sikertelen új scan nem teszi használhatatlanná az előző sikeres helyi
  adathalmazt.

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
- **Futtatás:** egy alkalmazás-image és egyetlen alkalmazásszolgáltatás; nincs
  külön queue, cache, alkalmazás-adatbázis vagy megfigyelési stack.
- **Frontend kiszolgálás:** a buildelt frontend statikus fájljait a FastAPI szolgálja ki.
- **Hosszú műveletek:** egyetlen folyamaton belüli háttértask; nincs Celery, Redis vagy külön worker.

### 4.2. Folyamatkorlátok

- Az alkalmazás egyetlen Uvicorn workerrel fusson, hogy az in-process feladatállapot egyértelmű legyen.
- Egyszerre legfeljebb egy adatgyűjtés vagy számításigényes elemzés futhat.
- Az olvasási API-k az adatgyűjtés közben a korábbi sikeres SQLite-fájlt használhatják.
- A frontend pollinggal kérdezze le a scan vagy elemzés állapotát; WebSocket/SSE nem szükséges.
- Leállításkor a folyamatban lévő művelet megszakított állapotot kap; az aktuális sikeres adatfájl nem sérülhet.

## 5. Egyszerű projektstruktúra

```text
oracle-graph-analyzer/
├── frontend/
│   ├── src/                 # React felület, API kliens és komponensek
│   └── package.json
├── backend/
│   ├── app/                 # API, Oracle scanner, gráf, elemzés, SQLite
│   ├── tests/
│   └── pyproject.toml
├── data/                    # egyetlen aktuális SQLite-adatfájl és exportok
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

Fejlesztéskor a frontend és backend külön indítható, de a felmérést végző
felhasználó számára csak a Docker Compose-os, egy alkalmazáskonténerből álló
futtatást kell dokumentálni. A cél Oracle lehet meglévő külső adatbázis vagy a
helyi Compose-ban indított példány.

## 6. Helyi SQLite-adatmodell

### 6.1. Táblák

| Tábla | Tartalom |
|---|---|
| `app_meta` | schema version, adatbázisazonosító, scan ideje, kiválasztott sémák |
| `scan_status` | aktuális művelet állapota, fázisa, számlálói és hibaüzenete |
| `objects` | az aktuális felmérés normalizált Oracle-objektumai |
| `relationships` | nyers, irányított és típusos kapcsolatok |
| `relationship_evidence` | a kapcsolat forrása és bizonyítéka |
| `analysis_runs` | az aktuális adathalmazon futtatott elemzések konfigurációi |
| `analysis_membership` | objektum és közösség megfeleltetés |
| `community_metrics` | közösségenként számított mutatók |
| `community_edges` | közösségek közötti aggregált élek |
| `centrality_results` | elemzésenkénti központisági értékek |
| `annotations` | helyi közösségnév és elemzői megjegyzés |
| `analysis_hierarchy*` | a kísérleti hierarchia fája és levéltagságai |
| `export_jobs` | az aktuális munkamenetben készített exportok állapota |

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

A jelszó csak a helyi, git által nem követett `.env` fájlban jelenjen meg. Ne
kerüljön SQLite-ba, API-válaszba vagy exportba.

### 7.2. Kapcsolatpróba és capabilities

A kapcsolatpróba adja vissza:

- Oracle-verzió;
- adatbázis és container/PDB neve;
- kapcsolódási mód;
- elérhető sémák;
- a scannerhez szükséges olvasható `ALL_*` nézetek;
- elérhető objektumtípusok;
- figyelmeztetések a hiányzó nézetjogokra.

A scope kizárólag a read-only metadata felhasználó által látható `ALL_*`
nézetekre épül. `DBA_*` jogosultság és külön adminisztrátori üzemmód nem része
a tervnek. A kiválasztott sémák listája minden releváns lekérdezésben bind
változóként szerepeljen.

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

Elsődleges forrás: `ALL_OBJECTS`.

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
| Constraint-ek | `ALL_CONSTRAINTS` | FK-kapcsolat |
| Constraint-oszlopok | `ALL_CONS_COLUMNS` | FK forrás/cél oszloplista |
| Indexek | `ALL_INDEXES` | `INDEX_ON` kapcsolat |
| Triggerek | `ALL_TRIGGERS` | `TRIGGER_ON` + metadata |
| Synonymok | `ALL_SYNONYMS` | `POINTS_TO` vagy külső placeholder |

Az `ALL_OBJECTS` által látható egyéb típusok generikus node-ként megmaradnak,
de nem kapnak külön extractort csak azért, hogy minden lehetséges Oracle
objektumtípushoz saját metadata-modell tartozzon.

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

### 8.7. Forráskód és dinamikus SQL határa

A kapcsolatok a katalógusnézetekből származnak. PL/SQL- vagy SQL-parser,
forráskódtárolás és heurisztikus dinamikus-SQL-felismerés nem része ennek a
helyi elemzőeszköznek. Az ilyen hivatkozások hiánya ismert korlátként jelenjen
meg; kézi vizsgálatuk a felmérés része lehet.

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
- teljes futási idő.

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
| `TRIGGER_ON` | 4.0 | szoros életciklus-kapcsolat |
| `DEPENDS_ON` | 3.0 | általános katalógusfüggőség |
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

### 13.4. Ellenőrzési mód

Az alkalmazás közösségdetektáló algoritmusa Leiden. Louvain, Infomap, Label
Propagation és egy általános pluginfelület nem szükséges az egyszeri
felméréshez. A kontrollt több resolution, több seed, eltérő hub policy és a
minőségi mutatók összevetése adja.

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
- fölötte determinisztikus mintavételes közelítés használható;
- az eredmény jelezze, ha közelítés készült.

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
  "resolveExternalReferences": true,
  "synonymMaxDepth": 8
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

### 19.1. Munkaterületek

Nem szükséges külön route- és képernyőrendszer minden funkcióhoz. Egyetlen
áttekinthető oldalon négy munkaterület elegendő:

1. **Kapcsolat és adatgyűjtés:** connection test, sémaválasztás, scan progress és összesítő.
2. **Gráfböngésző:** keresés, részgráf, objektum- és kapcsolatrészlet, hatás és útvonal.
3. **Közösségelemzés:** paraméterezés, futások, mutatók, community map és drill-down.
4. **Export:** aktuális nézet vagy teljes elemzési eredmény.

### 19.2. Gráfinterakciók

- node-ra kattintás: detail panel;
- szomszédok betöltése bejövő, kimenő vagy mindkét irányban;
- node rögzítése és lokális elrendezés újrafuttatása;
- közösség szerinti színezés;
- objektumtípus szerinti alak vagy ikon;
- `INVALID` objektum külön kerettel/jelöléssel;
- bizonytalan él szaggatott vonallal;
- edge-re kattintva evidence és metadata;
- közösségi aggregált nézet és drill-down;
- „Miért került ide?” panel top belső élekkel és külső kapcsolati aránnyal.

### 19.3. Elrendezés

Egy jól működő Cytoscape automatikus elrendezés elegendő. A felhasználó
node-okat rögzíthet, és külön gombbal újrafuttathatja az elrendezést. Több
layout engine, szerveroldali pozíciószámítás és pozíciócache nem követelmény.

### 19.4. Elemzőt segítő UX

- alapértelmezett súlyprofil és rövid magyarázat minden paraméterhez;
- resolution presetek egy kattintással;
- az elemzési futások egymás melletti összehasonlítása;
- legjobb és legrosszabb conductance-ű közösségek gyors listája;
- top hubok és bridge-ek külön rangsora;
- schema–community mátrix;
- a paraméterek és eredmények exportálása együtt.

## 20. Export

Támogatandó formátumok:

- JSON: nodes, edges, analysis config, memberships és metrics;
- CSV: objektumok, kapcsolatok, közösségtagság, közösségmutatók és centralitás külön fájlokban;
- SVG/PNG: aktuális vizuális nézet.

Az export legyen determinisztikus sorrendű, hogy két manuálisan archivált futás fájlszinten is könnyebben összevethető legyen. Az Oracle-jelszó és connect string érzékeny részei soha ne kerüljenek exportba.

## 21. Teljesítmény és memória

### 21.1. Célméret

A scanner kötegelt módon ír SQLite-ba, az elemzés pedig a szűrt gráfot
memóriába tölti. Nincs általános nagygráf-platform cél: ha a céladatbázis nem
fér el biztonságosan a helyi gépen, owner-, objektumtípus- vagy
confidence-szűréssel kell szűkíteni. A konfigurálható hard limit ezt a gépet
védi, nem szolgáltatási SLA-t valósít meg.

### 21.2. Optimalizálási sorrend

1. Oracle-lekérdezések csak szükséges oszlopokkal és owner filterrel.
2. Kötegelt Oracle-olvasás és SQLite-írás.
3. Elemzés előtt egyetlen rendezett edge-lista betöltése.
4. Technikai objektumok alapértelmezett kizárása.
5. Connected componentenkénti Leiden-futtatás.
6. Frontenden limitált részgráf és közösségi összecsukás.

### 21.3. Erőforráskorlátok

- a scan megszakítható és opcionális időlimittel védhető;
- elemzés maximum node/edge limitje konfigurálható;
- hard UI-limitek a részgráfokra;
- memóriahiány esetén az elemzés kontrollált hibával álljon le, az SQLite-adat ne sérüljön;
- a frontend indítás előtt közelítő node/edge méretet jelezzen.

## 22. Hibakezelés

### 22.1. Oracle-hibák

- hibás hitelesítés: rövid, érthető üzenet és Oracle hibakód;
- hiányzó nézetjog: részleges capabilities és konkrét hiányzó nézet;
- kapcsolat megszakadása: scan `FAILED`, előző adathalmaz változatlan;
- opcionális katalógusnézet hiánya: warning; a fő objektum/dependency/FK forrás hiánya kontrollált hiba;
- timeout: az érintett fázis látszódjon a felületen.

### 22.2. Elemzési hibák

- üres elemzési gráf: paraméterezési magyarázat;
- csak izolált node-ok: nincs Leiden-futtatás, külön lista;
- negatív/null súly: konfigurációvalidációs hiba;
- túl nagy gráf: szűkítési javaslat;
- numerikus centralitási hiba: az adott mutató hibás, a többi eredmény megmaradhat;
- megszakítás: részleges membership ne váljon sikeres analysis runná.

### 22.3. Helyi diagnosztika

A művelet állapota, fázisa, számlálói és rövid hibája a felületen látszik. A
normál konzolkimenet fejlesztői hibakereséshez elegendő; külön fájllog,
logrotáció, strukturált auditlog, metrika- vagy tracing-rendszer nem része a
tervnek. Jelszó és teljes connect descriptor semmilyen kimenetre nem kerülhet.

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

### 23.2. Oracle smoke próba

Nem szükséges külön, tartósan üzemeltetett golden Oracle-környezet és minden
Oracle-objektumtípust lefedő integrációs tesztmátrix. A tényleges felmérés
előtt egy kis, eldobható próbasémán vagy a célrendszer ismert mintáján elég
ellenőrizni:

- két owner azonos nevű objektumának elkülönítését;
- egy sémák közötti dependency vagy FK megőrzését;
- egy trigger, index és synonym kapcsolatát;
- egy külső hivatkozás placeholderét.

A scanner lekérdezési és normalizálási logikájának többi ága helyi fixture-ös
teszttel ellenőrizhető, Oracle-konténer nélkül.

### 23.3. Gráfalgoritmus-regresszió

Kis, rögzített tesztgráfok:

- két erős közösség egy bridge-dzsel;
- három közösség közös hubbal;
- izolált node-ok;
- párhuzamos és többtípusú élek;
- ciklus és több disconnected component;
- schema-határokat átlépő közösség.

Fix input + konfiguráció + seed esetén ellenőrizendő a membership, quality és fő közösségmutatók. Könyvtárfrissítéskor a változást tudatosan kell felülvizsgálni.

### 23.4. SQLite és újrafuttatási tesztek

- üres adatfájl inicializálása;
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

### 23.6. Gyakorlati elfogadási próba

Az elemző a tényleges céladatbázison végigjárja a rendes munkafolyamatot:

1. elindítja az alkalmazást, kapcsolatot tesztel és lefuttat egy scant;
2. néhány ismert objektumot és kapcsolatot visszaellenőriz az Oracle-ben;
3. futtat egy alap- és egy összehasonlító közösségelemzést;
4. megnyit egy közösséget, egy hatáselemzést és egy útvonalat;
5. exportálja a használni kívánt eredményt.

Nincs előírt objektum-, kapcsolat-, profil- vagy közösségdarabszám: a próba
célja annak igazolása, hogy a konkrét felmérés elvégezhető.

## 24. Megvalósítási prioritás

A terv nem vállalati projektütemezés és nem tartalmaz mesterséges hétbecslést.
A fejlesztési sorrend a használható eredményhez igazodik:

1. **Biztos kinyerés:** read-only kapcsolat, többsémás scanner, stabil ID,
   alapkapcsolatok, placeholder és atomikus SQLite-csere.
2. **Elemzői érték:** kereshető gráf, hatás/útvonal, Leiden, mutatók,
   összehasonlítás és community drill-down.
3. **Átadás:** export, rövid használati útmutató, automatizált regressziós
   tesztek és egy gyakorlati próba a céladatbázison.

Új funkció csak akkor kerül a tervbe, ha a konkrét felméréshez szükséges; az
általános platformépítés nem önálló cél.

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
| Dinamikus SQL nem látható | hiányzó kapcsolatok | ismert korlát jelzése és szükség esetén kézi ellenőrzés |
| Technikai objektumok torzítanak | félrevezető közösségek | alapértelmezett kizárás/összevonás |
| Közös hubok összerántják a modulokat | túl nagy közösségek | hubnormalizálás és kontrollfutás |
| Resolution önkényes | instabil felosztás | preset sorozat, több seed és mutatók |
| Nagy gráf memóriaigénye | sikertelen elemzés | komponensek, szűrés, hard limit és előzetes becslés |
| Egyetlen SQLite-fájl sérülése | eredményvesztés | `.next.db`, integrity check és atomikus csere |
| Közösség tévesen üzleti modulnak tűnik | rossz következtetés | magyarázható mutatók és emberi értelmezés |
| Synonym/DB link nem oldható fel | hiányos célkapcsolat | placeholder node és warning |
| Dockerből nem érhető el Oracle | alkalmazás használhatatlan | connection test, hálózati dokumentáció, szükség esetén host gateway |

## 27. Az egyszeri felmérés előkészítése

1. Kijelölni a céladatbázist és a felmérendő sémákat.
2. Létrehozni vagy ellenőrizni a read-only metadata felhasználót.
3. Kipróbálni a kapcsolatot és ellenőrizni a szükséges `ALL_*` nézeteket.
4. Lefuttatni a scant, majd néhány ismert objektummal és kapcsolattal
   visszaellenőrizni a lefedettséget.
5. Az első értelmezhető eredményen beállítani a súlyokat, hub policy-t és
   resolutiont, majd exportálni a felmérés eredményét.

## 28. Hivatalos technikai hivatkozások

- [Oracle – schema object dictionary views](https://docs.oracle.com/en/database/oracle/oracle-database/26/admin/managing-schema-objects.html)
- [python-oracledb – kapcsolatkezelés](https://python-oracledb.readthedocs.io/en/stable/user_guide/connection_handling.html)
- [python-igraph – Graph API és Leiden](https://igraph.org/python/versions/latest/api/igraph.Graph.html)
- [Cytoscape.js – hivatalos dokumentáció](https://js.cytoscape.org/)

## 29. Összegzés

A megoldás szándékosan egyszerű futtatási és tárolási modellt használ: egy
alkalmazáskonténerben futó FastAPI backend és React frontend, valamint egyetlen
SQLite-fájl. Ez elhagyja a többfelhasználós és vállalati üzemeltetési
rétegeket, de nem egyszerűsíti le a felmérés szakmai magját.

A rendszer értékét a megbízható több-sémás Oracle-kinyerés, a bizonyítékokkal ellátott forrásgráf, a konfigurálható elemzési gráf és a magyarázható közösségdetektálás együtt adja. Az alkalmazás akkor tekinthető sikeresnek, ha az elemző nemcsak egy látványos hálózatot kap, hanem meg tudja válaszolni: mely objektumok tartoznak szorosan össze, miért kerültek egy csoportba, mennyire különülnek el, mely elemek kötik össze a csoportokat, és milyen függőségi következményekkel járhat egy objektum módosítása.
