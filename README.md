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
- egyszolgáltatásos Docker Compose futtatás, egy Uvicorn workerrel.

## Következő mérföldkő

Az elemzési pipeline: technikai node policy, package spec/body elemzési összevonás, súlyozás, confidence és párhuzamos edge aggregáció, hubkezelés, szimmetrizálás, majd reprodukálható Leiden-futtatások és közösségmutatók. A scanner további finomítása során készül el a korlátozott mélységű synonym-láncfeloldás; a gráfböngészőben pedig bővülnek az interaktív kapcsolat- és confidence-szűrők.

Részletes terv: [oracle-adatbazis-graf-megvalositasi-terv.md](oracle-adatbazis-graf-megvalositasi-terv.md)
