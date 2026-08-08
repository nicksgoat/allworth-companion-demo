"""Household document vault with authenticated API streaming.

The storage root must be an encrypted persistent volume in production. File
bytes never enter Azure Synapse or application logs; metadata is kept beside the
household prefix so deletion can be complete and independently verified.
"""

from __future__ import annotations

from datetime import datetime, timezone
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock
from uuid import UUID, uuid4

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContentSettings


MAX_FILE_BYTES = int(os.getenv("VAULT_MAX_FILE_BYTES", str(25 * 1024 * 1024)))
BLOCKED_EXTENSIONS = {".exe", ".dll", ".com", ".bat", ".cmd", ".ps1", ".sh", ".js", ".jar"}


class VaultService:
    def __init__(self):
        self.root = Path(os.getenv("VAULT_STORAGE_PATH", "/tmp/planengine-vault")).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock = RLock()

    def _household_dir(self, household_id: UUID) -> Path:
        path = self.root / str(household_id)
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return path

    def _metadata_path(self, household_id: UUID) -> Path:
        return self._household_dir(household_id) / "metadata.json"

    def _load(self, household_id: UUID) -> list[dict]:
        path = self._metadata_path(household_id)
        if not path.exists(): return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, household_id: UUID, records: list[dict]) -> None:
        path = self._metadata_path(household_id)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(records, indent=2), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(path)

    def list(self, household_id: UUID, client_visible_only: bool = False) -> list[dict]:
        with self._lock:
            rows = self._load(household_id)
            return [row for row in rows if not client_visible_only or row["shared_with_client"]]

    def add(self, household_id: UUID, name: str, mime: str, content: bytes,
            actor: str, folder: str, shared_with_client: bool) -> dict:
        safe_name = re.sub(r"[^A-Za-z0-9._() -]", "_", Path(name).name).strip() or "document"
        if Path(safe_name).suffix.lower() in BLOCKED_EXTENSIONS:
            raise ValueError("executable file types are not accepted")
        if not content: raise ValueError("empty files are not accepted")
        if len(content) > MAX_FILE_BYTES: raise ValueError("file exceeds vault size limit")
        file_id = uuid4()
        record = {"id": str(file_id), "household_id": str(household_id),
                  "folder": folder, "name": safe_name,
                  "mime": mime or "application/octet-stream", "size": len(content),
                  "uploaded_by": actor, "sha256": sha256(content).hexdigest(),
                  "shared_with_client": shared_with_client,
                  "created_at": datetime.now(timezone.utc).isoformat()}
        with self._lock:
            target = self._household_dir(household_id) / f"{file_id}.bin"
            target.write_bytes(content); os.chmod(target, 0o600)
            records = self._load(household_id); records.append(record)
            self._save(household_id, records)
        return record

    def get(self, household_id: UUID, file_id: UUID) -> tuple[dict, bytes]:
        with self._lock:
            record = next((row for row in self._load(household_id)
                           if row["id"] == str(file_id)), None)
        if record is None: raise KeyError(file_id)
        path = self._household_dir(household_id) / f"{file_id}.bin"
        if not path.is_file(): raise KeyError(file_id)
        return record, path.read_bytes()

    def set_shared(self, household_id: UUID, file_id: UUID, shared: bool) -> dict:
        with self._lock:
            records = self._load(household_id)
            record = next((row for row in records if row["id"] == str(file_id)), None)
            if record is None: raise KeyError(file_id)
            record["shared_with_client"] = shared
            self._save(household_id, records)
            return record

    def delete(self, household_id: UUID, file_id: UUID) -> None:
        with self._lock:
            records = self._load(household_id)
            remaining = [row for row in records if row["id"] != str(file_id)]
            if len(remaining) == len(records): raise KeyError(file_id)
            path = self._household_dir(household_id) / f"{file_id}.bin"
            if path.exists(): path.unlink()
            self._save(household_id, remaining)

    def purge(self, household_id: UUID) -> int:
        with self._lock:
            path = self.root / str(household_id)
            if not path.exists(): return 0
            count = len(list(path.glob("*.bin")))
            for child in path.iterdir(): child.unlink()
            path.rmdir()
            return count


class AzureBlobVaultService:
    """Azure Blob implementation for multi-instance production deployments."""

    def __init__(self, connection_string: str, container_name: str):
        self.container = BlobServiceClient.from_connection_string(connection_string).get_container_client(container_name)
        self._lock = RLock()

    def _ensure_container(self):
        try: self.container.create_container()
        except ResourceExistsError: pass

    @staticmethod
    def _blob_name(household_id: UUID, file_id: UUID) -> str:
        return f"{household_id}/{file_id}.bin"

    @staticmethod
    def _encode(record: dict) -> dict[str, str]:
        encoded = base64.urlsafe_b64encode(json.dumps(record).encode()).decode()
        return {"planengine_record": encoded}

    @staticmethod
    def _decode(metadata: dict | None) -> dict:
        encoded = (metadata or {}).get("planengine_record")
        if not encoded: raise ValueError("vault blob metadata is missing")
        return json.loads(base64.urlsafe_b64decode(encoded.encode()))

    def list(self, household_id: UUID, client_visible_only: bool = False) -> list[dict]:
        try:
            rows = [self._decode(blob.metadata) for blob in self.container.list_blobs(
                name_starts_with=f"{household_id}/", include=["metadata"])]
        except ResourceNotFoundError:
            return []
        return [row for row in rows if not client_visible_only or row["shared_with_client"]]

    def add(self, household_id: UUID, name: str, mime: str, content: bytes,
            actor: str, folder: str, shared_with_client: bool) -> dict:
        safe_name = re.sub(r"[^A-Za-z0-9._() -]", "_", Path(name).name).strip() or "document"
        if Path(safe_name).suffix.lower() in BLOCKED_EXTENSIONS:
            raise ValueError("executable file types are not accepted")
        if not content: raise ValueError("empty files are not accepted")
        if len(content) > MAX_FILE_BYTES: raise ValueError("file exceeds vault size limit")
        file_id = uuid4()
        record = {"id": str(file_id), "household_id": str(household_id), "folder": folder,
                  "name": safe_name, "mime": mime or "application/octet-stream",
                  "size": len(content), "uploaded_by": actor, "sha256": sha256(content).hexdigest(),
                  "shared_with_client": shared_with_client,
                  "created_at": datetime.now(timezone.utc).isoformat()}
        self._ensure_container()
        self.container.get_blob_client(self._blob_name(household_id, file_id)).upload_blob(
            content, overwrite=False, metadata=self._encode(record),
            content_settings=ContentSettings(content_type=record["mime"]))
        return record

    def get(self, household_id: UUID, file_id: UUID) -> tuple[dict, bytes]:
        blob = self.container.get_blob_client(self._blob_name(household_id, file_id))
        try:
            properties = blob.get_blob_properties()
            return self._decode(properties.metadata), blob.download_blob().readall()
        except ResourceNotFoundError as exc:
            raise KeyError(file_id) from exc

    def set_shared(self, household_id: UUID, file_id: UUID, shared: bool) -> dict:
        blob = self.container.get_blob_client(self._blob_name(household_id, file_id))
        try: record = self._decode(blob.get_blob_properties().metadata)
        except ResourceNotFoundError as exc: raise KeyError(file_id) from exc
        record["shared_with_client"] = shared
        blob.set_blob_metadata(self._encode(record))
        return record

    def delete(self, household_id: UUID, file_id: UUID) -> None:
        try: self.container.delete_blob(self._blob_name(household_id, file_id))
        except ResourceNotFoundError as exc: raise KeyError(file_id) from exc

    def purge(self, household_id: UUID) -> int:
        try: names = [blob.name for blob in self.container.list_blobs(name_starts_with=f"{household_id}/")]
        except ResourceNotFoundError: return 0
        for name in names: self.container.delete_blob(name, delete_snapshots="include")
        return len(names)


_azure_connection = (os.getenv("VAULT_AZURE_CONNECTION_STRING") or "").strip()
vault_service = (AzureBlobVaultService(_azure_connection,
                                       os.getenv("VAULT_AZURE_CONTAINER", "planengine-vault"))
                 if _azure_connection else VaultService())
