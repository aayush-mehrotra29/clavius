"""Publish the reviewed illumination snapshot after verifying its recorded inputs.

Run explicitly after validation; normal numerical reruns do not replace the
snapshot linked from the app's Data & models dialog.
"""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    path = ROOT / "docs/validation/observed-shadow-comparison.json"
    report = json.loads(path.read_text())
    for name, expected in report["implementation_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("Implementation changed since the comparison: " + name)
    if digest(ROOT / "docs/validation/observed-shadow-protocol.json") != report["protocol_sha256"]:
        raise ValueError("Protocol changed since the comparison")
    for asset in report["sample_derivatives"]:
        if digest(path.parent / asset["file"]) != asset["sha256"]:
            raise ValueError("Sample derivative changed since the comparison")
    current = json.loads((ROOT / "public/data/simulation-manifest.json").read_text())["observed_shadow_validation"]
    if current != report["source_manifest_section"]:
        raise ValueError("Scientific source specification changed since the comparison")
    destination = ROOT / "public/data/illumination-validation.json"
    shutil.copyfile(path, destination)
    manifest_path = ROOT / "public/data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["simulation"]["observed_shadow_validation"]["report"] = {"url": "/data/illumination-validation.json", "sha256": digest(destination), "bytes": destination.stat().st_size, "model_id": report["model_id"], "status": "Bounded comparisons recorded; numerical targets are not all met. No operational accuracy bound.", "script": "scripts/publish_shadow_validation.py"}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print("Published hash-verified illumination snapshot", digest(destination))


if __name__ == "__main__":
    main()
