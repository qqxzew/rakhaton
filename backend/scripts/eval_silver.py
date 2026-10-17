"""Silver-standard evaluation of prior-reference extraction (no hand labels needed).

Silver gold: comparison phrases that a strict regex can read unambiguously from the report text,
e.g. "ve srovnání s CT z 3. 4. 26" -> (CT, 2026-04-03). These are a high-precision subset of all
citations, so the numbers measure recall/accuracy of the LLM extraction on clear cases; they are
labeled "silver standard", not a hand-labeled gold set.

Metrics (printed, and saved to data/eval/silver.json; counts only, no text or ids):
- recall: share of silver citations the LLM also extracted with the same modality family and date
- date accuracy: among silver citations with a same-modality extraction, share with the exact date
- in-dataset share: silver citations that match an internal study (the rest are older or external)
- naive baseline: share of silver citations equal to "latest internal study of the same modality
  before the report" (what a rule without reading the text would pick)

    FHIR_BACKEND=local uv run python scripts/eval_silver.py --patients 80 --max-reports 150
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import date

from app.config import get_settings
from app.fhir_store.factory import get_store
from app.llm.client import GatewayBackend, LlmError, StructuredLlm
from app.pipeline.extract_priors import extract_references
from app.pipeline.normalize import normalize_modality
from app.pipeline.timeline import build_studies

MOD = r"(CT|MRI?|PET(?:\s*/\s*CT)?|RTG|SONO|USG|UZ|MAMO|MG)"
SILVER = re.compile(
    r"(?:srovn[áa]n[íi]|porovn[áa]n[íi]|oproti|srovn[áa]no|porovn[áa]no)\s+(?:s|se)?\s*"
    r"(?:p[řr]edchoz[íi]m|minul[ýy]m|posledn[íi]m)?\s*" + MOD +
    r"[^.;\n]{0,40}?\b(?:z|ze|ze\s+dne|dne|od)\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{2,4})",
    re.IGNORECASE,
)
FAMILY = {"PET": "PETCT", "CT": "PETCT"}  # PET/CT reports are often cited as CT and vice versa


def fam(m: str) -> str:
    return FAMILY.get(m, m)


def silver_items(text: str) -> list[tuple[str, date]]:
    out = []
    for m in SILVER.finditer(text):
        mod = normalize_modality(m.group(1).replace(" ", ""))
        d, mo, y = int(m.group(2)), int(m.group(3)), int(m.group(4))
        y = y + 2000 if y < 100 else y
        try:
            out.append((mod, date(y, mo, d)))
        except ValueError:
            continue
    return list(dict.fromkeys(out))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patients", type=int, default=80)
    ap.add_argument("--max-reports", type=int, default=150)
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args()

    store = get_store()
    llm = StructuredLlm(GatewayBackend())
    ids = store.list_patient_ids()
    random.Random(args.seed).shuffle(ids)

    n_reports = n_silver = recalled = same_mod = date_ok = in_dataset = naive_hit = 0
    llm_refs_total = llm_refs_dated = failed = 0
    patients_used = 0
    for pid in ids:
        if patients_used >= args.patients or n_reports >= args.max_reports:
            break
        studies, docs = build_studies(store, pid)
        reports = [d for d in docs if d.kind == "radiology_report" and d.date and silver_items(d.text)]
        if not reports:
            continue
        patients_used += 1
        for rep in reports:
            if n_reports >= args.max_reports:
                break
            n_reports += 1
            gold = silver_items(rep.text)
            try:
                refs, _ = extract_references(llm, rep, pid)
            except LlmError:
                failed += 1
                continue
            llm_refs_total += len(refs)
            got = []
            for r in refs:
                if r.ref_date and r.ref_date.day:
                    llm_refs_dated += 1
                    got.append((fam(r.modality), date(r.ref_date.year, r.ref_date.month, r.ref_date.day)))
            for mod, d in gold:
                n_silver += 1
                if (fam(mod), d) in got:
                    recalled += 1
                if any(gm == fam(mod) for gm, _ in got):
                    same_mod += 1
                    if any(gm == fam(mod) and abs((gd - d).days) == 0 for gm, gd in got):
                        date_ok += 1
                if any(fam(s.modality) == fam(mod) and abs((s.date - d).days) <= 3 for s in studies):
                    in_dataset += 1
                earlier = [s for s in studies if fam(s.modality) == fam(mod) and s.date < rep.date]
                if earlier and abs((max(earlier, key=lambda s: s.date).date - d).days) <= 3:
                    naive_hit += 1
        print(f"patients {patients_used}, reports {n_reports}, silver {n_silver}", file=sys.stderr)

    def pct(a: int, b: int) -> float | None:
        return round(100 * a / b, 1) if b else None

    result = {
        "patients": patients_used, "reports": n_reports, "silver_citations": n_silver,
        "llm_failed_reports": failed, "llm_references": llm_refs_total, "llm_references_with_day_date": llm_refs_dated,
        "recall_pct": pct(recalled, n_silver),
        "modality_found_pct": pct(same_mod, n_silver),
        "date_accuracy_given_modality_pct": pct(date_ok, same_mod),
        "in_dataset_pct": pct(in_dataset, n_silver),
        "naive_latest_same_modality_pct": pct(naive_hit, n_silver),
        "note": "silver standard = strict regex citations; quotes are always verified as exact substrings",
    }
    out = get_settings().data_dir / "eval"
    out.mkdir(parents=True, exist_ok=True)
    (out / "silver.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
