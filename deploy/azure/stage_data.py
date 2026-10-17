"""Copy only the listed (demo) patients' FHIR bundles, without lab Observations (never goes into git)."""
import json
import shutil
import sys
from pathlib import Path

demo, fhir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
ids = [p["patient_id"] for p in json.loads(demo.read_text(encoding="utf-8"))["patients"]]
shutil.copy(demo, out / "demo_patients.json")
(out / "raw" / "fhir").mkdir(parents=True, exist_ok=True)
for pid in ids:
    b = json.loads((fhir / f"{pid}.json").read_text(encoding="utf-8"))
    b["entry"] = [e for e in b.get("entry", []) if e.get("resource", {}).get("resourceType") != "Observation"]
    (out / "raw" / "fhir" / f"{pid}.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
print(f"staged {len(ids)} patients")
