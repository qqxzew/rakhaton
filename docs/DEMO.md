# Demo runbook (T090)

Everything runs locally. Patient data stays on this machine.

## 0. Start (about 2 minutes)

```bash
docker compose up -d                                   # IRIS for Health + Mailpit (data volume keeps everything)
docker compose -f docker-compose.yml -f docker-compose.dicom.yml up -d orthanc-motol orthanc-nnh orthanc-homolka orthanc-fnm
cd backend && uv run python scripts/iris_setup.py      # idempotent: FHIR endpoints, search limit, production
uv run python scripts/dicom_iris_setup.py              # once: IRIS namespace PACSDICOM (C-FIND client)
uv run python scripts/seed_dicom.py                    # idempotent: synthetic blank DICOM studies into the 4 Orthanc (demo + cloud + review patients)
uv run python scripts/demo_reset.py                    # backup + clean state + 3 demo patients + nightly run
uv run uvicorn app.main:app --reload --port 8000       # backend (keep running)
cd ../frontend && npm run dev                          # frontend on http://localhost:5173 (restart it after a pull!)
```

Check: `http://localhost:8000/api/health` shows `backend: iris, patients: 1830` and `pacs.status: ok` (all four Orthanc answer, a C-FIND through IRIS works). Mailpit: `http://localhost:8025`; Orthanc (simulated ePACS) UI: `http://localhost:8051` (Motol), 8052 NNH, 8053 Homolka, 8054 FNM.

Image availability is checked by the system itself: study-level DICOM C-FIND against these Orthanc (`AVAILABILITY_ADAPTER` empty = `dicom`). If a PACS does not answer, the item falls back to the hospital FHIR endpoints / dataset flag with a warning in the log and `availability_source` set on the item; the pipeline never stops. Leave `AVAILABILITY_ADAPTER` empty in `.env` (an old `fhir_hospitals` line switches the check back).
Backup video of the whole flow: `data/demo/pacs_komparator_demo.mp4` (2:08, Czech voice-over).

## 1. At the customer's table (3 minutes, in Czech)

| Step | Screen | Say / do |
|---|---|---|
| 1 | Přehled MDT | "Koordinátor vidí konzilia na 7 dní. Noční běh dva dny předem už připravil žádosti." Point at the red meeting and the banner "Noční běh: N žádostí ke schválení". |
| 2 | Day → patient with planned PET (Homolka) | The patient page shows only name, year of birth and one row per comparison study with three states: **Připraveno**, **Čeká na odpověď** (when and how it was requested), **Vyžaduje pozornost** (cannot be obtained, or delivered and waiting for confirmation). "Koordinátor vidí jen to, co potřebuje." Then "Zobrazit podrobnosti": "Plánované PET jsme našli v ambulantní zprávě – tady je přesná citace." Click the quote. |
| 3 | Podrobnosti → Požadovaná předchozí vyšetření | "AI přečetla nálezy: CT existuje, ale snímky nejsou v PACS. Starší PET je zmíněné v nálezu, u nás chybí – přes FHIR jsme zjistili, že ho má FNM." Click the quote "Ve srovnání s PET/CT…". |
| 4 | Dashboard → Schválit vše | "Koordinátor jen schválí. E-mail obsahuje jen minimum údajů." Show Mailpit. |
| 5 | Posunout čas +24 h (twice) | "Bez odpovědi přijde připomínka, pak automatický hovor – bez identity pacienta." Open "Zobrazit žádost" (e-mail, reminder, voice transcript). |
| 6 | Row "Simulace" → Simulovat odpověď / doručení | "Nemocnice pošle studii přes IHE MHD, systém ověří, že odpovídá." The row turns **Vyžaduje pozornost – snímky dorazily**; click "Potvrdit převzetí" (and "Vzít na vědomí" on any open issue in Podrobnosti) → **Připraveno**. |
| 6b | Patient → **Nahrát testovací nález** | "Ať vidíte, že to běží naživo: nahrajeme nový nález (soubor .txt nebo vzorový text), uloží se do IRIS FHIR a AI ho hned přečte." Takes about 20 s; the cited PET/CT appears as a new missing study. Afterwards **Odstranit testovací nálezy** in the same dialog restores the case. |
| 7 | Ask | "Jdeme správným směrem? Co by vám ještě chybělo?" |

Numbers to say (Statistiky page, silver standard over 120 reports / 121 unambiguous citations): AI finds **99 %** of cited prior studies, dates **100 %** correct, every quote verified verbatim. Only **41 %** of cited priors exist in Motol data; a naive "latest study of the same modality" rule finds only **35 %** → reading the report text is the point.

## 2. For the InterSystems judges (2 minutes)

1. **Integrace** page: FHIR server counts (`/fhir/r4` + hospital endpoints), production items, last messages → click a session → **Visual Trace** (login SuperUser/SYS).
2. **Management Portal**: `http://localhost:52773/csp/sys/UtilHome.csp` → Interoperability → `PacsComparator.Production`.
3. **FHIR**: `http://localhost:52773/fhir/r4/Task?_count=5` – our Task/Communication/Provenance/AuditEvent resources.
4. **SQL**: FHIR SQL Builder projection `PacsProjection.*` (Statistiky page shows the numbers it computes).
5. **Vector Search** box on Integrace (multilingual embeddings computed locally, stored in IRIS `VECTOR`).
6. **HL7 v2** button (ORM from a simulated RIS → FHIR ServiceRequest, visible in Visual Trace) and **DICOM C-FIND** button.
7. **IntegratedML**: Žádosti page shows late-arrival probability and expected hours (trained on a synthetic, labeled history).
8. **MCP agent**: chat in the patient view – "Které snímky chybí a kde jsou?".

## 3. If something breaks

- Dashboard shows a CSS error → restart `npm run dev` (Tailwind config changed).
- Patient Search returns 413 / FHIR "too costly" → rerun `uv run python scripts/iris_setup.py`.
- Test reports left over → the dialog's "Odstranit testovací nálezy", or `demo_reset.py` (deletes all of them).
- Requests stuck after experiments → `uv run python scripts/demo_reset.py` (backup in `data/backup/`).
- Voice uses the premade ElevenLabs voice set in `.env` (`ELEVENLABS_VOICE_ID`); free plan quota is limited, the transcript always works.
