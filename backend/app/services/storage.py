import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class UploadStorage(Protocol):
    def write(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalUploadStorage:
    def __init__(self, root: Path | None = None):
        self.root = (root or get_settings().upload_dir).resolve()

    def path(self, key: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}\.csv", key):
            raise ValueError("Invalid server storage key")
        return self.root / key

    def write(self, key: str, data: bytes):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(key)
        # Publish only fully flushed content. Hard-link creation is atomic and exclusive:
        # it does not overwrite a pre-existing final file, unlike os.replace().
        descriptor, name = tempfile.mkstemp(prefix=f".{key}.", suffix=".tmp", dir=self.root)
        temporary = Path(name)
        published = False
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, path)
            published = True
            temporary.unlink()
        except BaseException:
            if published:
                path.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
            raise

    def read(self, key: str) -> bytes:
        with self.path(key).open("rb") as stream:
            data = stream.read(get_settings().max_upload_bytes + 1)
        if len(data) > get_settings().max_upload_bytes:
            raise ValueError("Stored file exceeds configured maximum")
        return data

    def delete(self, key: str):
        self.path(key).unlink(missing_ok=True)
