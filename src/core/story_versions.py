"""Immutable local snapshots and semantic diffs, including legacy numbered backups."""
import hashlib
import copy
import json
import os
from pathlib import Path
import tempfile
from uuid import NAMESPACE_URL, uuid4, uuid5


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".wenyoo-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class StoryVersions:
    def __init__(self, directory, story_id):
        self.directory = Path(directory)
        self.story_id = story_id
        self.directory.mkdir(parents=True, exist_ok=True)

    def list(self):
        versions = []
        for path in self.directory.glob(f"{self.story_id}_*.yaml"):
            number = path.stem[len(self.story_id) + 1:]
            if not number.isdigit():
                continue
            stat = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            metadata = {}
            if path.with_suffix(".json").exists():
                metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            versions.append({
                "version": int(number), "filename": path.name, "size": stat.st_size,
                "uuid": metadata.get("uuid", str(uuid5(NAMESPACE_URL, f"wenyoo:{self.story_id}:{number}:{digest}"))),
                "timestamp": metadata.get("timestamp", stat.st_mtime),
                "summary": metadata.get("summary", "Legacy saved version"),
                "sha256": digest,
            })
        return sorted(versions, key=lambda v: v["version"])

    def resolve(self, version):
        for entry in self.list():
            if str(entry["version"]) == str(version) or entry["uuid"] == str(version):
                return self.directory / entry["filename"]
        raise FileNotFoundError(f"Version '{version}' not found")

    def snapshot(self, text, summary):
        versions = self.list()
        number = max((v["version"] for v in versions), default=-1) + 1
        # Exclusive creation prevents two saves from overwriting the same snapshot.
        while True:
            path = self.directory / f"{self.story_id}_{number}.yaml"
            try:
                with path.open("x", encoding="utf-8") as handle:
                    handle.write(text)
                break
            except FileExistsError:
                number += 1
        metadata = {"uuid": str(uuid4()), "timestamp": path.stat().st_mtime,
                    "summary": summary[:500], "version": number}
        atomic_write(path.with_suffix(".json"), json.dumps(metadata, ensure_ascii=False))
        return metadata


def _canonical_story(data):
    """Ignore editor-populated defaults that do not change authored behavior."""
    data = copy.deepcopy(data)
    for key in ("objects", "characters", "actions", "triggers", "forms", "functions", "initial_variables", "connections"):
        if data.get(key) in ([], {}):
            data.pop(key, None)
    nodes = data.get("nodes", {})
    if isinstance(nodes, dict):
        for key, node in nodes.items():
            if not isinstance(node, dict):
                continue
            if node.get("id") == key:
                node.pop("id")
            for field in ("objects", "actions", "triggers", "properties", "groups", "hints"):
                if node.get(field) in ([], {}):
                    node.pop(field, None)
    return data


def story_diff(before, after):
    """Compare entity lists by ID so ordering does not disguise an actual edit."""
    changes = []
    missing = object()

    def visit(old, new, path):
        if old is missing or new is missing:
            changes.append({"kind": "added" if old is missing else "removed", "path": path,
                            "before": None if old is missing else old, "after": None if new is missing else new})
        elif isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(old.keys() | new.keys()):
                if key not in ("connection_graph_source_md5", "current_connection_graph_source_md5", "connection_graph_status"):
                    visit(old.get(key, missing), new.get(key, missing), path + [key])
        elif isinstance(old, list) and isinstance(new, list) and all(
            isinstance(v, dict) and isinstance(v.get("id"), str) for v in old + new
        ) and len({v["id"] for v in old}) == len(old) and len({v["id"] for v in new}) == len(new):
            visit({v["id"]: v for v in old}, {v["id"]: v for v in new}, path)
        elif old != new:
            changes.append({"kind": "modified", "path": path, "before": old, "after": new})

    visit(_canonical_story(before), _canonical_story(after), [])
    counts = {kind: sum(c["kind"] == kind for c in changes) for kind in ("added", "removed", "modified")}
    return {"changes": changes, "counts": counts}
