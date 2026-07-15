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
- külső és távoli célok placeholder node-jai, determinisztikus élek és külön evidence-rekordok;
- scan lefedettségi összesítő owner-, objektumtípus- és kapcsolattípus-számlálókkal;
- megszakításbiztos staging pipeline, idegenkulcs- és endpoint-validálás, majd atomikus publikálás;
- React/TypeScript kapcsolat-, sémaválasztó-, scanállapot- és összesítő képernyő;
- facettált objektumkereső, objektum- és kapcsolatrészlet API evidence adatokkal;
- irány-, kapcsolattípus- és confidence-szűrt, szerveroldalon limitált részgráf API;
- ciklusbiztos dependents/dependencies hatáselemzés és hopszám- vagy súlyalapú útvonalkeresés;
- Cytoscape gráfböngésző node/edge detail panellel, impact- és útvonalindítással;
- külön raw és analysis gráfréteg, owner-/objektumtípus-/confidence-szűréssel és package spec/body elemzési összevonással;
- konfigurálható kapcsolattípus-súlyozás, párhuzamosél-aggregáció, súlycap, technikai node policy és háromféle hubkezelés;
- irányított metrikagráf és szimmetrizált közösséggráf, izolált és megosztott infrastruktúra státusszal;
- komponensenként futó, fix seed mellett reprodukálható Leiden CPM/modularity elemzés és hatpontos resolution profil;
- közösségi density, conductance, coverage, belső/külső súly, séma- és objektumtípus-eloszlás, valamint schema-határ összesítések;
- PageRank, weighted strength, in/out degree, betweenness, articulation point, bridge edge és k-core mutatók;
- atomikusan mentett, megszakítható és újra lekérdezhető elemzési futások, közösségi drill-down és aggregált community graph API;
- böngészős Leiden-indítás, resolution profil, futáslista, megszakítás/törlés és közösségi eredménytábla;
- egyszolgáltatásos Docker Compose futtatás, egy Uvicorn workerrel.

## Következő mérföldkő

Az 5. fázis elemzői és validációs funkciói következnek: az aggregált community graph vizualizációja, resolution- és futás-összehasonlító táblák/görbék, schema–community mátrix, közösségnév-javaslatok és annotációk, többseedes stabilitásvizsgálat, valamint JSON/CSV/SVG/PNG export. Ezzel párhuzamosan készül el a golden Oracle séma és a szélesebb algoritmusregresszió, a teljesítménymérés, a korlátozott mélységű synonym-láncfeloldás és a gráfböngésző további interaktív szűrése.

Részletes terv: [oracle-adatbazis-graf-megvalositasi-terv.md](oracle-adatbazis-graf-megvalositasi-terv.md)
