"""Simulated RIS (T086): sends synthetic HL7 v2 ORM^O01 (planned exam) and ORU^R01 (report) to IRIS.

IRIS turns them into a FHIR ServiceRequest / DiagnosticReport in /fhir/r4, tagged as simulation
(production items PacsComparator.HL7.*). Transports:

  iris-mllp (default)  the IRIS native API opens an MLLP connection to the inbound service inside the container
                       (port 4561 is not published) and prints the ACK type
  mllp                 plain MLLP socket to --host/--port (use when the port is published)
  file                 drops a .hl7 file into the folder of the file service inside the container

    uv run python scripts/simulate_ris.py --kind both [--patient ID] [--modality CT] [--days 14]
    uv run python scripts/simulate_ris.py --print-only

The patient defaults to the first demo patient (data/demo_patients.json). Order numbers and report text are
synthetic; patient ids are never printed.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from datetime import date, datetime, timedelta

import iris

from app.config import get_settings
from app.exchange.hl7 import DICOM_CODES, Order, Report, build_orm, build_oru, message_type

NAMESPACE = "FHIRSERVER"
REGIONS = {"CT": ("chest", "abdomen", "pelvis"), "MR": ("brain",), "PET": ("whole_body",), "RTG": ("chest",),
           "SONO": ("abdomen",), "MAMO": ("breast",), "SCINT": ("whole_body",)}
SERVICE_TEXT = {"CT": "CT hrudníku, břicha a pánve", "MR": "MR mozku", "PET": "PET/CT celého těla",
                "RTG": "RTG plic", "SONO": "SONO břicha", "MAMO": "MAMO", "SCINT": "Scintigrafie skeletu"}
REPORT_LINES = ("Simulovaný nález (syntetický text pro ukázku).",
                "Srovnání s předchozím vyšetřením není v tomto syntetickém textu uvedeno.",
                "Závěr: bez nových změn.")


def demo_patient() -> str:
    data = json.loads((get_settings().data_dir / "demo_patients.json").read_text(encoding="utf-8"))
    return data["patients"][0]["patient_id"]


def build_messages(patient: str, kind: str, modality: str, days: int, run_id: str,
                   now: datetime | None = None) -> list[str]:
    placer = f"SIM-ORD-{run_id}"
    messages: list[str] = []
    if kind in ("orm", "both"):
        order = Order(patient, placer, modality, REGIONS[modality], SERVICE_TEXT[modality],
                      date.today() + timedelta(days=days))
        messages.append(build_orm(order, now))
    if kind in ("oru", "both"):
        report = Report(patient, f"SIM-RPT-{run_id}", modality, SERVICE_TEXT[modality], REPORT_LINES,
                        placer_order=placer, observed=date.today())
        messages.append(build_oru(report, now))
    return messages


def mllp_socket(host: str, port: int, message: str) -> str:
    frame = b"\x0b" + message.encode("utf-8") + b"\x1c\r"
    with socket.create_connection((host, port), timeout=10) as sock:
        sock.sendall(frame)
        data = sock.recv(65536)
    return data.decode("utf-8", errors="replace").strip("\x0b\x1c\r")


def ack_status(ack: str) -> str:
    """Acknowledgement code of an ACK (MSA-1: AA accept, AE/AR error) or the error text."""
    for segment in ack.replace("\n", "\r").split("\r"):
        if segment.startswith("MSA|"):
            return segment.split("|")[1]
    return ack[:80] or "no ACK"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["orm", "oru", "both"], default="both")
    parser.add_argument("--patient", help="patient id (default: first demo patient)")
    parser.add_argument("--modality", choices=sorted(DICOM_CODES), default="CT")
    parser.add_argument("--days", type=int, default=14, help="planned date = today + N days (ORM)")
    parser.add_argument("--transport", choices=["iris-mllp", "mllp", "file"], default="iris-mllp")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=4561, help="MLLP port (inside the container for iris-mllp)")
    parser.add_argument("--iris-port", type=int, default=1972)
    parser.add_argument("--print-only", action="store_true", help="print the messages and send nothing")
    args = parser.parse_args(argv)

    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    patient = args.patient or demo_patient()
    messages = build_messages(patient, args.kind, args.modality, args.days, run_id)
    if args.print_only:
        for message in messages:
            print(message.replace("\r", "\n").replace(patient, "<patient>"))
        return 0

    conn = None
    irispy = None
    if args.transport != "mllp":
        conn = iris.createConnection(args.host, args.iris_port, NAMESPACE, "SuperUser", "SYS")
        irispy = iris.createIRIS(conn)
    try:
        for message in messages:
            kind = message_type(message)
            if args.transport == "mllp":
                result = f"ACK {ack_status(mllp_socket(args.host, args.port, message))}"
            elif args.transport == "iris-mllp":
                ack = irispy.classMethodValue("PacsComparator.HL7.Api", "SendMllp", message, args.port)
                result = f"ACK {ack_status(str(ack))}"
            else:
                name = f"{kind.replace('^', '_')}-{run_id}.hl7"
                result = f"file {irispy.classMethodValue('PacsComparator.HL7.Api', 'DropFile', name, message)}"
            print(f"{kind}: {result}", file=sys.stderr)
            time.sleep(1)
    finally:
        if conn:
            conn.close()
    print(f"run id {run_id}: order SIM-ORD-{run_id}, report SIM-RPT-{run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
