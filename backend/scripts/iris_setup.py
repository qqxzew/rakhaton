"""Create the FHIR R4 server inside InterSystems IRIS for Health (no sample data).

Run after the IRIS container from the InterSystems FHIR-AI-Hackathon-Kit is up. Unlike the kit's
own setup script, this one does NOT load the kit's synthetic Synthea bundles; our dataset is
loaded separately by scripts/load_iris.py.

    uv run python scripts/iris_setup.py [--host localhost] [--port 1972]
"""

from __future__ import annotations

import argparse
import sys
import time

import iris

NAMESPACE = "FHIRSERVER"
ENDPOINT = "/fhir/r4"
STRATEGY = "HS.FHIRServer.Storage.JsonAdvSQL.InteractionsStrategy"
PACKAGE = "hl7.fhir.r4.core@4.0.1"


def connect(host: str, port: int, namespace: str, user: str, password: str):
    conn = iris.createConnection(host, port, namespace, user, password)
    return conn, iris.createIRIS(conn)


def wait_for_iris(host: str, port: int, user: str, password: str, timeout: int) -> None:
    start = time.monotonic()
    while True:
        try:
            conn, _ = connect(host, port, "%SYS", user, password)
            conn.close()
            return
        except Exception as exc:  # noqa: BLE001 - driver raises plain exceptions while starting
            if time.monotonic() - start > timeout:
                raise SystemExit(f"IRIS not reachable on {host}:{port}: {exc}") from exc
            time.sleep(3)


def raise_search_limit(irispy, limit: int = 100000) -> None:
    """The server refuses searches that select more than 1000 resources ("SearchTooCostly")."""
    strategy = irispy.classMethodObject("HS.FHIRServer.API.InteractionsStrategy", "GetStrategyForEndpoint", ENDPOINT)
    config = strategy.invokeObject("GetServiceConfigData")
    if int(config.get("MaxSearchResults") or 0) < limit:
        config.set("MaxSearchResults", limit)
        strategy.invokeVoid("SaveServiceConfigData", config)
        print(f"MaxSearchResults set to {limit}", file=sys.stderr)


def create_fhir_server(host: str, port: int, user: str, password: str) -> None:
    conn, irispy = connect(host, port, "HSLIB", user, password)
    try:
        if not irispy.classMethodBoolean("%SYS.Namespace", "Exists", NAMESPACE):
            print(f"creating namespace {NAMESPACE} (takes a minute)", file=sys.stderr)
            irispy.classMethodVoid("HS.Util.Installer.Foundation", "Install", NAMESPACE)
    finally:
        conn.close()

    conn, irispy = connect(host, port, NAMESPACE, user, password)
    try:
        if irispy.classMethodBoolean("HS.FHIRServer.ServiceInstance", "ExistsByUrl", ENDPOINT):
            print(f"FHIR endpoint {ENDPOINT} already exists", file=sys.stderr)
            raise_search_limit(irispy)
            return
        print(f"installing FHIR R4 endpoint {ENDPOINT}", file=sys.stderr)
        irispy.classMethodVoid("HS.FHIRServer.Installer", "InstallNamespace")
        irispy.classMethodVoid("HS.FHIRServer.Installer", "InstallInstance", ENDPOINT, STRATEGY, PACKAGE)
        raise_search_limit(irispy)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1972)
    parser.add_argument("--user", default="SuperUser")
    parser.add_argument("--password", default="SYS")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    wait_for_iris(args.host, args.port, args.user, args.password, args.timeout)
    create_fhir_server(args.host, args.port, args.user, args.password)
    print(f"FHIR base: http://{args.host}:52773{ENDPOINT}", file=sys.stderr)


if __name__ == "__main__":
    main()
