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

4. Nyisd meg a [http://localhost:8000](http://localhost:8000) címet, futtasd a kapcsolatpróbát, válaszd ki a sémákat, majd indítsd el az adatgyűjtést.

Az aktuális munkafájl a host `data/oracle_graph.db` fájlja. A scanner futás közben külön `oracle_graph.next.db` fájlt épít, és csak sikeres integritásellenőrzés után cseréli le atomikusan az aktuális adatot. A jelszó nem kerül bele az adatbázisba és API-válaszba.

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
- React/TypeScript kapcsolat-, sémaválasztó-, scanállapot- és összesítő képernyő;
- facettált objektumkereső, objektum- és kapcsolatrészlet API evidence adatokkal;
- irány-, kapcsolattípus- és confidence-szűrt, szerveroldalon limitált részgráf API;
- ciklusbiztos dependents/dependencies hatáselemzés és hopszám- vagy súlyalapú útvonalkeresés;
- Cytoscape gráfböngésző node/edge detail panellel, impact- és útvonalindítással, státusz-, kapcsolattípus-, confidence- és külsőobjektum-szűréssel;
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
- böngészős Leiden-indítás, resolution profil, futáslista, megszakítás/törlés és közösségi eredménytábla;
- ötfutásos seed-stabilitásprofil Adjusted Rand Index, NMI, Variation of Information, node-szintű együttklaszterezési stabilitás és dokumentált közösségcímkék számításával;
- automatikus közösségnév-javaslat domináns séma, névtokenek és központi TABLE/PACKAGE alapján, magyarázattal és helyi elemzői annotációval;
- interaktív, összecsukott community map, schema–community mátrix, conductance-rangsor, top hub/bridge és „Miért került ide?” nézet;
- kijelölt futások összehasonlító táblája és resolution-görbéje, valamint címkefüggetlen particionálási egyezésmutatók;
- determinisztikus JSON, CSV-csomag, SVG és PNG elemzésexport, státusz- és letöltési API-val, árva fájlok automatikus takarításával;
- egyszolgáltatásos Docker Compose futtatás, egy Uvicorn workerrel.

## Elemzői munkafolyamat

1. Indíts egy önálló Leiden-futást, egy hatpontos resolution-profilt vagy az öt seedből álló stabilitásprofilt.
2. Jelölj ki legalább két sikeres futást a futáslistában, majd hasonlítsd össze a paramétereket, a közösségszámot, quality/conductance értékeket, valamint az ARI/NMI/VI egyezést.
3. Nyiss meg egy futást, és használd a community mapet, a schema–community mátrixot és a legjobb/legrosszabb conductance listát. A közösségre kattintva megjelenik a névjavaslat indoklása, a top hubok és bridge-ek.
4. A javasolt nevet helyi címkével és elemzői megjegyzéssel írhatod felül. Ezek az aktuális SQLite-adathalmazhoz tartoznak, új scan után nem öröklődnek tovább.
5. A JSON export a konfigurációt, node-okat, kapcsolatokat, tagságokat és mutatókat együtt tartalmazza; a CSV ZIP külön táblákat ad, a futásexport SVG/PNG formátuma determinisztikus aggregált közösségi térképet készít. A gráfok saját „Aktuális nézet” gombjai ezzel szemben pontosan a pillanatnyi interaktív pan/zoomot és node-pozíciókat mentik.

A stabilitási címke alapértelmezett küszöbei: `STABLE ≥ 0,80`, `MIXED ≥ 0,55`, ez alatt `UNSTABLE`. A node-pontszám legfeljebb tíz, az elemzési gráfban megmaradó fő szomszéddal való együttklaszterezés gyakorisága a seed-futások között.

## Következő mérföldkő

Az 5. fázis fennmaradó validációs és hardening feladatai következnek: a becslési memóriaformula valós Oracle-adathalmazokon történő kalibrálása, golden Oracle séma és szélesebb algoritmusregresszió, Docker Compose tiszta-adatkönyvtár próba, valamint a felhasználói elfogadási forgatókönyv. A funkcionális tervből még hátravan a kísérleti hierarchikus közösségelemzés.

Részletes terv: [oracle-adatbazis-graf-megvalositasi-terv.md](oracle-adatbazis-graf-megvalositasi-terv.md)
