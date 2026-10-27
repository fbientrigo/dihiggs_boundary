#!/usr/bin/env python3
"""Create or verify the immutable 125.13 adaptive-boundary archive manifest."""

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path


MANIFEST = "ARCHIVE_MANIFEST.json"
INVENTORY = "SHA256SUMS.tsv"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def files(root):
    return (path for path in sorted(root.rglob("*")) if path.is_file() and path.name not in {MANIFEST, INVENTORY})


def write_manifest(source, archive):
    source, archive = Path(source).resolve(), Path(archive).resolve()
    inventory = archive / INVENTORY
    with inventory.open("w", encoding="utf-8") as handle:
        handle.write("path\tsize_bytes\tsha256\n")
        for path in files(source):
            relative = path.relative_to(source)
            handle.write(f"{relative}\t{path.stat().st_size}\t{sha256(path)}\n")
    payload = {
        "schema": "dihiggs.historical_archive.v1",
        "source_path": str(source),
        "archive_path": str(archive),
        "acquired_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "convention": {"id": "mh_125p13_pdg_2026_historical_replay", "m_h_GeV": "125.13", "status": "historical_only"},
        "policy": "Historical geometry may schedule fresh 125.20 work but its rows, fractions, intervals, and survivor classifications are never pooled.",
        "sha256_inventory": INVENTORY,
    }
    (archive / MANIFEST).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify(source, archive):
    source, archive = Path(source).resolve(), Path(archive).resolve()
    manifest = json.loads((archive / MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("source_path") != str(source) or manifest.get("convention", {}).get("status") != "historical_only":
        raise ValueError("archive manifest is not the historical 125.13 campaign")
    expected = {}
    for line in (archive / manifest["sha256_inventory"]).read_text(encoding="utf-8").splitlines()[1:]:
        relative, size, digest = line.split("\t")
        expected[relative] = (int(size), digest)
    actual = {str(path.relative_to(source)): (path.stat().st_size, sha256(path)) for path in files(source)}
    copied = {str(path.relative_to(archive)): (path.stat().st_size, sha256(path)) for path in files(archive)}
    if expected != actual or expected != copied:
        raise ValueError("historical archive checksum inventory does not match source and copy")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    verify(args.source, args.archive) if args.verify else write_manifest(args.source, args.archive)
