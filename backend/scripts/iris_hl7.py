"""Install the simulated-RIS HL7 v2 feed (T086) in the running production, without restarting it.

Uploads and compiles iris/src (like scripts/iris_production.py), then applies the changed production
definition with Ens.Director.UpdateProduction (the new items PacsComparator.HL7.*: MLLP service on port 4561
inside the container, file service on /tmp/pacs-hl7/in/, routing process, backend hook).

    uv run python scripts/iris_hl7.py [--hook-url http://host.docker.internal:8106/api/hooks/fhir-written]
"""

from __future__ import annotations

import argparse
import sys

import iris

from scripts.iris_production import NAMESPACE, load_classes, upload_sources

HOOK_ITEM = "PacsComparator.HL7.BO.BackendHook"


def apply(host: str = "localhost", port: int = 1972, user: str = "SuperUser", password: str = "SYS",
          hook_url: str | None = None) -> str:
    conn = iris.createConnection(host, port, NAMESPACE, user, password)
    try:
        irispy = iris.createIRIS(conn)
        print(f"uploaded {upload_sources(irispy)} class files", file=sys.stderr)
        load_classes(irispy)
        if hook_url:
            result = irispy.classMethodValue("PacsComparator.HL7.Admin", "SetHookUrl", hook_url)
            print(f"hook url: {result}", file=sys.stderr)
        result = irispy.classMethodValue("PacsComparator.HL7.Admin", "Apply")
        print(f"production update: {result}", file=sys.stderr)
        return str(result)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1972)
    parser.add_argument("--hook-url", help="override HookUrl of the backend hook item (stored in the production)")
    args = parser.parse_args()
    apply(args.host, args.port, hook_url=args.hook_url)


if __name__ == "__main__":
    main()
