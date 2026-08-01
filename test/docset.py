#!/usr/bin/env python3
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
docroot = root / "docs" / "time-authority"
manifest_text = (docroot / "docset.yaml").read_text(encoding="utf-8")
if "schema: aiwg.pagenbar.docset/v1" not in manifest_text:
    raise SystemExit("unsupported docset schema")
routes = re.findall(r"(?m)^  - id: ([a-z0-9-]+)\n    file: ([A-Za-z0-9._-]+)$", manifest_text)
route_ids = set()
required = {"id", "title", "summary", "audience", "tasks", "status", "version", "last_reviewed", "read_when"}
link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")

for route_id, filename in routes:
    if route_id in route_ids:
        raise SystemExit(f"duplicate route id: {route_id}")
    route_ids.add(route_id)
    path = docroot / filename
    if not path.is_file():
        raise SystemExit(f"missing route file: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise SystemExit(f"missing YAML front matter: {path}")
    front, body = text[4:].split("\n---\n", 1)
    metadata_keys = set(re.findall(r"(?m)^([a-z_]+):", front))
    missing = required - metadata_keys
    if missing:
        raise SystemExit(f"{path} missing metadata: {sorted(missing)}")
    if "Pagenbar:" not in body:
        raise SystemExit(f"{path} missing Pagenbar navigation")
    for target in link_pattern.findall(body):
        if "://" in target or target.startswith("#") or target.startswith("mailto:"):
            continue
        local = (path.parent / target.split("#", 1)[0]).resolve()
        if not local.exists():
            raise SystemExit(f"broken link in {path.name}: {target}")

print(f"docset ok: {len(routes)} routes")
