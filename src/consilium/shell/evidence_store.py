"""Content-addressed evidence for new artifacts. Historical acceptance is untouched."""
import hashlib
import os
import tempfile
from pathlib import Path


class EvidenceStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes) -> str:
        if type(content) is not bytes:
            raise ValueError('Evidence must preserve original bytes')
        digest = hashlib.sha256(content).hexdigest()
        target = self.root / digest
        if target.is_symlink():
            raise ValueError('Evidence object cannot be a symlink')
        if target.exists():
            if target.read_bytes() != content:
                raise ValueError('Evidence hash collision or damaged object')
            return digest
        fd, name = tempfile.mkstemp(dir=self.root, prefix='pending-')
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            # Exclusive link prevents a concurrent writer overwriting an object.
            try:
                os.link(name, target)
            except FileExistsError:
                if target.is_symlink() or target.read_bytes() != content:
                    raise ValueError('Existing evidence object is inconsistent') from None
        finally:
            Path(name).unlink(missing_ok=True)
        return digest

    def read(self, digest: str) -> bytes:
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid evidence digest')
        path = self.root / digest
        if path.is_symlink():
            raise ValueError('Evidence object cannot be a symlink')
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError('Evidence object checksum mismatch')
        return content
