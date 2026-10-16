"""Install the request-loop production (PacsComparator.*) in the FHIRSERVER namespace of IRIS (T081, T082).

Idempotent: uploads iris/src/**/*.cls over the native API (no docker needed), loads and compiles
them, stores the credentials the production needs (IRIS user for the FHIR endpoints, LLM gateway key,
optional ElevenLabs key; values come from the git-ignored .env and are never written to a file) and
starts the production, or applies the changed definition when it already runs.

    uv run python scripts/iris_production.py [--host localhost] [--port 1972]

Also called by scripts/iris_setup.py.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import iris

from app.config import REPO_ROOT, get_settings

NAMESPACE = "FHIRSERVER"
SOURCE_DIR = REPO_ROOT / "iris" / "src"
REMOTE_DIR = "/tmp/pacs-comparator-src"


def upload_sources(irispy, source_dir: Path = SOURCE_DIR, remote_dir: str = REMOTE_DIR) -> int:
    """Write every class file to the IRIS host (UTF-8) so that it can be loaded from disk."""
    count = 0
    for path in sorted(source_dir.rglob("*.cls")):
        remote = f"{remote_dir}/{path.relative_to(source_dir).as_posix()}"
        irispy.classMethodValue("%File", "CreateDirectoryChain", remote.rsplit("/", 1)[0])
        stream = irispy.classMethodObject("%Stream.FileCharacter", "%New")
        stream.set("Filename", remote)
        stream.set("TranslateTable", "UTF8")
        stream.invokeVoid("Write", path.read_text(encoding="utf-8"))
        status = stream.invoke("%Save")
        if str(status) != "1":
            raise SystemExit(f"could not write {remote}: {status}")
        count += 1
    return count


def load_classes(irispy, remote_dir: str = REMOTE_DIR) -> None:
    status = irispy.classMethodValue("%SYSTEM.OBJ", "LoadDir", remote_dir, "ck", iris.IRISReference(""), 1)
    if str(status) != "1":
        text = irispy.classMethodValue("%SYSTEM.Status", "GetErrorText", status)
        raise SystemExit(f"loading the production classes failed: {text}")


def set_credentials(irispy, iris_user: str, iris_password: str) -> list[str]:
    settings = get_settings()
    wanted = {
        "PacsComparator.Iris": (iris_user, iris_password),
        "PacsComparator.Llm": ("api-key", settings.api_key),
        "PacsComparator.Voice": (os.environ.get("ELEVENLABS_VOICE_ID", "").strip(),
                                 os.environ.get("ELEVENLABS_API_KEY", "").strip()),
    }
    stored = []
    for name, (user, password) in wanted.items():
        if not password:
            print(f"credential {name}: no value in .env, skipped", file=sys.stderr)
            continue
        result = irispy.classMethodValue("PacsComparator.Req.Admin", "SetCredential", name, user, password)
        if result != "ok":
            raise SystemExit(f"credential {name} failed: {result}")
        stored.append(name)
    return stored


def install_production(host: str = "localhost", port: int = 1972, user: str = "SuperUser",
                       password: str = "SYS") -> str:
    conn = iris.createConnection(host, port, NAMESPACE, user, password)
    try:
        irispy = iris.createIRIS(conn)
        print(f"uploaded {upload_sources(irispy)} class files", file=sys.stderr)
        load_classes(irispy)
        print("production classes compiled", file=sys.stderr)
        print(f"credentials stored: {', '.join(set_credentials(irispy, user, password))}", file=sys.stderr)
        result = irispy.classMethodValue("PacsComparator.Req.Admin", "EnsureRunning")
        print(f"production PacsComparator.Production: {result}", file=sys.stderr)
        return str(result)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1972)
    parser.add_argument("--user", default="SuperUser")
    parser.add_argument("--password", default="SYS")
    args = parser.parse_args()
    install_production(args.host, args.port, args.user, args.password)


if __name__ == "__main__":
    main()
