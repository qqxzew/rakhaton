"""Install the DICOM C-FIND components in their own IRIS namespace PACSDICOM and start the test production (T087).

Nothing is touched in FHIRSERVER. Steps: create the Interoperability namespace (once), copy
infra/iris/pacsdicom/*.cls into the container's /tmp and load them, add the DICOM association contexts,
start the production PacsDicom.TestProduction. Safe to rerun.

    uv run python scripts/dicom_iris_setup.py [--container iris-fhir] [--stop]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import iris

NAMESPACE = "PACSDICOM"
PRODUCTION = "PacsDicom.TestProduction"
CLASS_DIR = Path(__file__).resolve().parents[2] / "infra" / "iris" / "pacsdicom"
REMOTE_DIR = "/tmp/pacsdicom"


def connect(namespace: str, host: str = "localhost", port: int = 1972, user: str = "SuperUser", pw: str = "SYS"):
    conn = iris.createConnection(host, port, namespace, user, pw)
    return conn, iris.createIRIS(conn)


def ensure_namespace() -> None:
    conn, irispy = connect("HSLIB")
    try:
        if irispy.classMethodBoolean("%SYS.Namespace", "Exists", NAMESPACE):
            print(f"namespace {NAMESPACE} exists", file=sys.stderr)
        else:
            print(f"creating namespace {NAMESPACE} (takes a minute)", file=sys.stderr)
            irispy.classMethodVoid("HS.Util.Installer.Foundation", "Install", NAMESPACE)
    finally:
        conn.close()


def copy_classes(container: str) -> None:
    subprocess.run(["docker", "exec", "-u", "root", container, "rm", "-rf", REMOTE_DIR], check=True)
    subprocess.run(["docker", "cp", str(CLASS_DIR), f"{container}:{REMOTE_DIR}"], check=True)


def load_and_start(stop: bool) -> None:
    conn, irispy = connect(NAMESPACE)
    try:
        sc = irispy.classMethodValue("%SYSTEM.OBJ", "LoadDir", REMOTE_DIR, "ck")
        if int(sc) != 1:
            raise SystemExit(f"class load failed: {irispy.classMethodValue('%SYSTEM.Status', 'GetErrorText', sc)}")
        print("classes loaded", file=sys.stderr)
        sc = irispy.classMethodValue("PacsDicom.Api", "Configure")
        if int(sc) != 1:
            text = irispy.classMethodValue("%SYSTEM.Status", "GetErrorText", sc)
            raise SystemExit(f"association setup failed: {text}")
        if stop:
            irispy.classMethodVoid("Ens.Director", "StopProduction")
            print("production stopped", file=sys.stderr)
            return
        running = irispy.classMethodValue("Ens.Director", "IsProductionRunning")
        if int(running or 0):
            irispy.classMethodVoid("Ens.Director", "UpdateProduction")
            print("production updated", file=sys.stderr)
        else:
            sc = irispy.classMethodValue("Ens.Director", "StartProduction", PRODUCTION)
            if int(sc) != 1:
                text = irispy.classMethodValue("%SYSTEM.Status", "GetErrorText", sc)
                raise SystemExit(f"production start failed: {text}")
            print(f"production {PRODUCTION} started", file=sys.stderr)
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="iris-fhir")
    parser.add_argument("--stop", action="store_true", help="stop the test production")
    args = parser.parse_args()
    ensure_namespace()
    copy_classes(args.container)
    load_and_start(args.stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
