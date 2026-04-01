"""Persistent room/session storage for resumable multiplayer sessions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import copy
import json
import logging
import os
import re
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)

ROOM_FILE_PREFIX = "room-"
ROOM_FILE_SUFFIX = ".json"


class PersistentSessionStore:
    """Filesystem-backed storage for persistent room snapshots."""

    def __init__(self, save_dir: str):
        self.base_dir = os.path.join(save_dir, "rooms")
        os.makedirs(self.base_dir, exist_ok=True)

    def _sanitize_filename_part(self, value: Optional[str]) -> str:
        raw = (value or "unknown").strip()
        sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)
        return sanitized or "unknown"

    def _room_path(self, room_id: str) -> str:
        filename = f"{ROOM_FILE_PREFIX}{self._sanitize_filename_part(room_id)}{ROOM_FILE_SUFFIX}"
        return os.path.join(self.base_dir, filename)

    def _atomic_write_json(self, path: str, payload: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=os.path.dirname(path),
            delete=False,
        ) as temp_file:
            json.dump(payload, temp_file, indent=2, ensure_ascii=False)
            temp_path = temp_file.name
        os.replace(temp_path, path)

    def _read_json_file(self, path: str) -> Optional[Dict[str, Any]]:
        try:
            with open(path, "r", encoding="utf-8") as file_obj:
                return json.load(file_obj)
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.error("Failed to read room file %s: %s", path, exc)
            return None

    def _iter_room_records(self) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for filename in os.listdir(self.base_dir):
            if not (filename.startswith(ROOM_FILE_PREFIX) and filename.endswith(ROOM_FILE_SUFFIX)):
                continue
            path = os.path.join(self.base_dir, filename)
            record = self._read_json_file(path)
            if not record or not isinstance(record, dict):
                continue
            records.append(record)
        return records

    def _room_matches_filters(
        self,
        record: Dict[str, Any],
        *,
        player_id: Optional[str] = None,
        story_id: Optional[str] = None,
    ) -> bool:
        if story_id and record.get("story_id") != story_id:
            return False

        if player_id:
            manifest = record.get("participant_manifest") or []
            manifest_ids = {
                entry.get("player_id") for entry in manifest if isinstance(entry, dict)
            }
            active_ids = set(record.get("participant_ids") or [])
            if player_id not in manifest_ids and player_id not in active_ids:
                return False

        return True

    def _build_room_listing(self, record: Dict[str, Any]) -> Dict[str, Any]:
        snapshot = record.get("snapshot") or {}
        transcript = record.get("transcript") or snapshot.get("transcript_history") or []
        participant_manifest = copy.deepcopy(record.get("participant_manifest") or [])
        preview = record.get("preview")

        if not preview and transcript:
            last_entry = transcript[-1]
            if isinstance(last_entry, dict):
                preview = last_entry.get("content") or ""
                if last_entry.get("is_html"):
                    preview = re.sub(r"<[^>]+>", "", preview)
                preview = str(preview).strip()

        return {
            "room_id": record.get("room_id"),
            "story_id": record.get("story_id"),
            "story_title": record.get("story_title"),
            "room_name": record.get("room_name") or record.get("story_title") or record.get("room_id"),
            "status": record.get("status", "archived"),
            "updated_at": record.get("updated_at") or "",
            "created_at": record.get("created_at") or "",
            "participant_manifest": participant_manifest,
            "participant_names": list(record.get("participant_names") or []),
            "participant_ids": list(record.get("participant_ids") or []),
            "current_node": record.get("current_node") or snapshot.get("current_node"),
            "preview": preview or "",
        }

    def save_room_record(self, room_id: str, record: Dict[str, Any]) -> None:
        payload = copy.deepcopy(record)
        payload["room_id"] = room_id
        payload["updated_at"] = datetime.now().isoformat()
        self._atomic_write_json(self._room_path(room_id), payload)

    def load_room_record(self, room_id: str) -> Optional[Dict[str, Any]]:
        return self._read_json_file(self._room_path(room_id))

    def room_exists(self, room_id: str) -> bool:
        return os.path.exists(self._room_path(room_id))

    def list_room_records(
        self,
        *,
        player_id: Optional[str] = None,
        story_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        records = []
        for record in self._iter_room_records():
            if not self._room_matches_filters(record, player_id=player_id, story_id=story_id):
                continue
            records.append(self._build_room_listing(record))

        records.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return records

    def delete_room(self, room_id: str) -> bool:
        path = self._room_path(room_id)
        if not os.path.exists(path):
            return False
        os.remove(path)
        return True

    def archive_all_rooms(self) -> None:
        changed = 0
        for record in self._iter_room_records():
            room_id = record.get("room_id")
            if not room_id:
                continue
            if record.get("status") == "active":
                record["status"] = "archived"
                self.save_room_record(room_id, record)
                changed += 1
        if changed:
            logger.info("Archived %s persisted rooms left active by a previous process.", changed)
