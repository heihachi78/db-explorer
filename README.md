# Oracle Graph Analyzer

Helyben futó, egyfelhasználós alkalmazás Oracle adatbázis-objektumok és kapcsolataik feltérképezésére. Az alkalmazás read-only Oracle kapcsolatból több kiválasztott sémát olvas be, majd a normalizált forrásgráfot egy helyi SQLite-fájlba publikálja.

## Gyors indítás

1. Másold le a környezeti mintát:

   ```bash
   cp .env.example .env
   ```

2. Töltsd ki az `ORACLE_USER`, `ORACLE_PASSWORD` és `ORACLE_DSN` értékeket. A felhasználó csak metaadat-olvasási jogokat kapjon.

3. Indítsd el az Oracle adatbázist és az alkalmazást:

   ```bash
   docker compose up --build
   ```

   A Compose az Oracle számára a meglévő, külső `ora-db-volume` named
   volume-ot csatolja az `/opt/oracle/oradata` könyvtárhoz. Az alkalmazás és
   az adatbázis közös Docker-hálózaton fut, ezért az Oracle DSN gépneve
   `ora-db` legyen.

4. Nyisd meg a [http://localhost:8000](http://localhost:8000) címet. Meglévő felmérés esetén előbb használd az „Új felmérés · minden adat törlése” műveletet, majd futtasd a kapcsolatpróbát, válaszd ki a sémákat és indítsd el az adatgyűjtést.

Az aktuális munkafájl a host `data/oracle_graph.db` fájlja. A scanner futás közben külön `oracle_graph.next.db` fájlt épít, és csak sikeres integritásellenőrzés után cseréli le atomikusan az aktuális adatot. A jelszó nem kerül bele az adatbázisba és API-válaszba.

Izolált, üres adatkönyvtáras próba indítható a meglévő felmérés érintése nélkül az `APP_DATA_HOST_DIR` átmeneti felülírásával; az alkalmazáson belüli útvonal továbbra is `/data` marad. Például egy már futó Compose Oracle mellett:

```bash
mkdir -p /tmp/db-explorer-smoke
APP_PORT=18001 APP_DATA_HOST_DIR=/tmp/db-explorer-smoke \
  docker compose run --rm --no-deps -p 18001:18001 oracle-graph-analyzer
```

## Helyi fejlesztés

Backend:

```bash
python3 -m venv .venv
.venv/bin/pip install -e './backend[dev]'
APP_DATA_DIR=./data .venv/bin/uvicorn app.main:app --app-dir backend --reload
```

Frontend külön terminálban:

```bash
cd frontend
npm install
npm run dev
```

A Vite fejlesztői szerver a `/api` hívásokat a `localhost:8000` backendhez továbbítja.

Tesztek:

```bash
.venv/bin/pytest -q backend/tests
cd frontend && npm test -- --run && npm run build
```

## Elkészült

- FastAPI alkalmazás egységes JSON hibaformával;
- érzékeny adatokat nem publikáló környezeti konfiguráció;
- Oracle Thin/Thick kapcsolatpróba és katalógus-capabilities riport;
- a teljes tervezett SQLite-séma kötelező indexekkel és WAL móddal;
- SQLite `integrity_check` és atomikus `.next.db` publikálási primitív;
- egyetlen párhuzamos hosszú műveletet engedő, megszakítható task manager;
- többsémás `ALL_OBJECTS` objektumkinyerés, stabil owner- és container-érzékeny azonosítókkal;
- `ALL_DEPENDENCIES`, összetett FK, trigger, index, helyi és releváns `PUBLIC` synonym kapcsolatok;
- konfigurálható mélységű synonym-láncfeloldás, feloldási útvonallal, ciklus- és mélységlimit-figyelmeztetéssel;
- külső és távoli célok placeholder node-jai, determinisztikus élek és külön evidence-rekordok;
- scan lefedettségi összesítő owner-, objektumtípus- és kapcsolattípus-számlálókkal;
- megszakításbiztos staging pipeline, idegenkulcs- és endpoint-validálás, majd atomikus publikálás;
- React/TypeScript kapcsolat-, séma- és opcionális objektumtípus-választó, scanállapot- és összesítő képernyő;
- egygombos, atomikus munkaterület-reset, amely együtt törli a metaadatokat, részgráfokat, elemzéseket, annotációkat és exportokat, és új scan előtt kötelező, ha már van publikált felmérés;
- facettált objektumkereső, objektum- és kapcsolatrészlet háttér-API evidence adatokkal;
- irány-, kapcsolattípus- és confidence-szűrt, szerveroldalon limitált részgráf API;
- ciklusbiztos dependents/dependencies hatáselemzés és hopszám- vagy súlyalapú útvonalkeresés;
- egyszerűsített Cytoscape gráfböngésző node/edge detail panellel és a természetes szerkezetre fókuszáló vezérlőkkel;
- a teljes publikált forrásgráf automatikus térképe gyengén összefüggő komponensekkel, fa/ciklusos/izolált szerkezeti jelöléssel, komponensméret-, név-, séma- és típusszűréssel, valamint többes komponenskijelöléssel;
- perzisztált, elnevezhető részgráfok szülő–gyermek eredettel; a közösségelemzés és annak méretbecslése kizárólag az aktív részgráf objektumaira és belső éleire fut;
- objektumtípusonként eltérő node-alakok, jobb kattintásos pozíciórögzítés és újrafuttatható gráfelrendezés;
- a pillanatnyi pan/zoomot és renderelt node-pozíciókat megőrző PNG-, illetve valódi vektoros SVG-nézetexport az objektumgráfból és a közösségi térképből;
- külön raw és analysis gráfréteg, owner-/objektumtípus-/confidence-szűréssel és package spec/body elemzési összevonással;
- konfigurálható kapcsolattípus-súlyozás, párhuzamosél-aggregáció, súlycap, technikai node policy és háromféle hubkezelés;
- irányított metrikagráf és szimmetrizált közösséggráf, izolált és megosztott infrastruktúra státusszal;
- komponensenként futó, fix seed mellett reprodukálható Leiden CPM/modularity elemzés és hatpontos resolution profil;
- közösségi density, conductance, coverage, belső/külső súly, séma- és objektumtípus-eloszlás, valamint schema-határ összesítések;
- PageRank, weighted strength, in/out degree, betweenness, articulation point, bridge edge és k-core mutatók;
- atomikusan mentett, megszakítható és újra lekérdezhető elemzési futások, közösségi drill-down és aggregált community graph API;
- konfigurálható scan-időkorlát, elemzési node/edge hard limit, kontrollált memóriahiba és futás előtti közelítő méret-/memóriabecslés;
- böngészős Leiden-indítás ésszerű modularity alapprofillal, részgráfonként szűrt futáslista, minden korábbi futás teljes paraméterkészlete, megszakítás/törlés és közösségi eredménytábla;
- ötfutásos seed-stabilitásprofil Adjusted Rand Index, NMI, Variation of Information, node-szintű együttklaszterezési stabilitás és dokumentált közösségcímkék számításával;
- automatikus közösségnév-javaslat domináns séma, névtokenek és központi TABLE/PACKAGE alapján, magyarázattal és helyi elemzői annotációval;
- interaktív, összecsukott community map, schema–community mátrix, conductance-rangsor, top hub/bridge és „Miért került ide?” nézet;
- közösségenként kereshető, lapozható objektumlista sémával, típussal, státusszal és centralitással, valamint csak a közösség node-jait és belső éleit mutató gráf;
- bármely közösség elnevezett gyermek-részgráffá alakítása és azon újabb közösségelemzés indítása;
- kísérleti hierarchikus közösségelemzés alacsony alap-resolutionnel, méretküszöb feletti rekurzív újrafelosztással, determinisztikus szülő–gyermek útvonalakkal, szülőnkénti resolution-felülírással, mélység- és közösségszám-limittel;
- perzisztált, összecsukható hierarchiafa helyi közösségmutatókkal és objektum-drill-downnal; a levéltagság egyszer tárolódik, a szülők tartalma leszármazotti lekérdezéssel áll elő;
- kijelölt futások összehasonlító táblája és resolution-görbéje, valamint címkefüggetlen particionálási egyezésmutatók;
- determinisztikus JSON, CSV-csomag, SVG és PNG elemzésexport, hierarchikus futásnál külön fa- és levéltagság-táblákkal, státusz- és letöltési API-val, árva fájlok automatikus takarításával;
- egyetlen aktuális exporteredmény: új export indításakor minden korábbi exportrekord és -fájl automatikusan törlődik;
- egyszolgáltatásos Docker Compose futtatás, egy Uvicorn workerrel.

## Elemzői munkafolyamat

1. Meglévő adatok esetén indíts új felmérést az egygombos resettel; ezután a teljes felület üres alapállapotból indul.
2. Ellenőrizd a kapcsolatot, válaszd ki a sémákat és objektumtípusokat, majd futtasd a metaadatgyűjtést.
3. A természetes gráftérképen szűrj minimum komponensméretre, névre, sémára, objektumtípusra vagy fa/ciklusos/izolált szerkezetre. Jelölj ki egy vagy több összefüggő komponenst, és szükség szerint csak egyet jeleníts meg vagy nagyíts ki.
4. Nevezd el és mentsd a kijelölt komponenseket részgráfként. Ettől kezdve a futások, becslések és eredmények kizárólag az aktív részgráfhoz tartoznak.
5. Indíts Leiden-futást az alapértelmezett modularity profillal, vagy módosítsd a resolutiont, seedet, confidence-küszöböt, hub policyt és élsúlyokat. A futáslista minden mentett paramétert megmutat.
6. Nyiss meg egy közösséget; a részletes, kereshető listában ellenőrizd a sémákat, objektumokat, típusokat, státuszokat és centralitásokat, a közösségi belső gráfon pedig ezek kapcsolatait.
7. Ha egy közösséget tovább akarsz bontani, nevezd el és mentsd gyermek-részgráfként, aktiváld, majd ismételd meg rajta az elemzést. Ez tetszőleges mélységben ismételhető.
8. Szükség esetén hasonlíts össze azonos részgráfhoz tartozó futásokat, adj elemzői címkét vagy megjegyzést, és exportáld az eredményt.

A stabilitási címke alapértelmezett küszöbei: `STABLE ≥ 0,80`, `MIXED ≥ 0,55`, ez alatt `UNSTABLE`. A node-pontszám legfeljebb tíz, az elemzési gráfban megmaradó fő szomszéddal való együttklaszterezés gyakorisága a seed-futások között.

## Átadási állapot

A karcsúsított terv funkcionális követelményei elkészültek. A 2026-07-15-i átadási próbán a production Docker image üres adatkönyvtárból indult, Oracle 23.26.2 adatbázishoz read-only módban kapcsolódott, majd a kapcsolat → többsémás scan → kontrollminta → Leiden-elemzés → JSON-export folyamat sikeresen végigfutott. A próba 740 objektumot és 924 forráskapcsolatot gyűjtött; az elemzés 502 csomóponton és 302 aggregált élen 305 közösséget készített.

Az automatikus regresszió 48 backend- és 17 frontendtesztből áll; a frontend production buildje sikeres. Más céladatbázis használatakor a kézi kontrollminta megismétlése továbbra is a felmérés része, nem külön fejlesztési vagy üzemeltetési projekt. Golden Oracle-környezet, általános nagygráf-benchmark, tartós fájllog és vállalati üzemeltetési réteg nem része a scope-nak.

Részletes terv: [oracle-adatbazis-graf-megvalositasi-terv.md](oracle-adatbazis-graf-megvalositasi-terv.md)
