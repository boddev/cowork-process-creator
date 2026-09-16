"""Development-only reproducible N00 artifacts. Never shipped as a runtime dependency."""
from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
from pathlib import Path

from make_fixtures import write_fixtures, write_if_new_or_same

ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "appPackage" / "skills" / "build-output-plugin" / "scripts" / "creator_builder.py"


def main() -> None:
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--metadata-dir", required=True, type=Path, help="Approved metadata for cowork-process-creator.json and ready-items-report.json")
    args = parser.parse_args()
    module_spec = importlib.util.spec_from_file_location("creator_builder", BUILDER_PATH)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError("Cannot locate bundled builder")
    builder = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(builder)
    metadata = {}
    identities = set()
    for name in ("cowork-process-creator", "ready-items-report"):
        path = args.metadata_dir / (name + ".json")
        supplied = builder.publishing_metadata(path)
        builder.require(supplied["app_id"] not in identities, "Creator and output require distinct supplied app_id values")
        identities.add(supplied["app_id"])
        metadata[name] = path
    dist = (args.output or ROOT / "dist" / ("n00-v" + builder.VERSION)).resolve()
    dist.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="creator-n00-") as directory:
        staging = Path(directory)
        for name, source, identity in (
            ("creator-n00", ROOT / "appPackage", "cowork-process-creator"),
            ("output-n00", ROOT / "examples" / "n00" / "candidate", "ready-items-report"),
        ):
            report = builder.build(source, staging / (name + ".zip"), staging / (name + ".report.json"), builder.TARGET, metadata[identity])
            for suffix in (".zip", ".report.json"):
                destination = dist / (name + suffix)
                write_if_new_or_same(destination, (staging / (name + suffix)).read_bytes())
            print(f"{name}.zip: {report['status']} / {report['size_bytes']} bytes / {report['sha256']}")
    for path in write_fixtures(dist / "n00-fixtures"):
        print(path)
    print("Developer artifacts only. Native N00 gate is not established by this command.")


if __name__ == "__main__":
    main()
