# Oracle Graph Analyzer

Helyben futó, egyfelhasználós alkalmazás Oracle adatbázis-objektumok és kapcsolataik feltérképezésére. A jelenlegi első mérföldkő az alkalmazásvázat, a helyi SQLite-tárolást és a read-only Oracle kapcsolatpróbát valósítja meg.

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

4. Nyisd meg a [http://localhost:8000](http://localhost:8000) címet, majd futtasd a kapcsolatpróbát.

Az aktuális munkafájl a host `data/oracle_graph.db` fájlja. A jelszó nem kerül bele az adatbázisba és API-válaszba.

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

## Elkészült ebben a mérföldkőben

- FastAPI alkalmazás egységes JSON hibaformával;
- érzékeny adatokat nem publikáló környezeti konfiguráció;
- Oracle Thin/Thick kapcsolatpróba és katalógus-capabilities riport;
- a teljes tervezett SQLite-séma kötelező indexekkel és WAL móddal;
- SQLite `integrity_check` és atomikus `.next.db` publikálási primitív;
- egyetlen párhuzamos hosszú műveletet engedő, megszakítható task manager;
- React/TypeScript kapcsolat- és állapotképernyő;
- egyszolgáltatásos Docker Compose futtatás, egy Uvicorn workerrel.

## Következő mérföldkő

A többsémás scanner: `ALL_OBJECTS`, `ALL_DEPENDENCIES`, FK-k, triggerek, indexek és synonymok kinyerése, normalizálása és atomikus publikálása.

Részletes terv: [oracle-adatbazis-graf-megvalositasi-terv.md](oracle-adatbazis-graf-megvalositasi-terv.md)
