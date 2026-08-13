# -*- coding: utf-8 -*-
#
# codimension - SSH remote project open/create (Qt-free)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Remote-first project open/create over SFTP.

Profiles (non-secret) live under ``~/.codimension3/ssh_hosts.json``.
Passwords go to the OS keyring (preferred) or ``ssh_password_<id>`` mode 0600.
Local working copies are cached under ``~/.codimension3/remote-projects/<id>/``.

Paramiko is optional at import time; call :func:`require_paramiko` before live use.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import posixpath
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Optional, Protocol, Sequence, runtime_checkable

from utils.atomic_io import atomic_write_text
from utils.settings import SETTINGS_DIR

HOSTS_FILENAME = "ssh_hosts.json"
BINDING_FILENAME = "binding.json"
KEYRING_SERVICE = "codimension-ssh"
TOKEN_FILE_MODE = 0o600

# Conservative MVP limits for recursive download.
MAX_REMOTE_FILES = 5000
MAX_REMOTE_BYTES = 200 * 1024 * 1024
SKIP_DIR_NAMES = frozenset({".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules"})

_SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(frozen=True)
class SshHostProfile:
    """Non-secret SSH host profile."""

    id: str
    host: str
    port: int = 22
    user: str = ""
    auth: str = "key"  # key | password
    identity_file: str = ""
    label: str = ""

    def normalized(self) -> "SshHostProfile":
        """Validate and normalize fields."""
        host = (self.host or "").strip()
        if not host:
            raise ValueError("host must be non-empty")
        auth = (self.auth or "key").strip().lower()
        if auth not in ("key", "password"):
            raise ValueError("auth must be 'key' or 'password'")
        port = int(self.port or 22)
        if port < 1 or port > 65535:
            raise ValueError("port out of range")
        pid = (self.id or "").strip() or _make_profile_id(host, self.user, port)
        return SshHostProfile(
            id=pid,
            host=host,
            port=port,
            user=(self.user or "").strip(),
            auth=auth,
            identity_file=os.path.expanduser((self.identity_file or "").strip()),
            label=(self.label or "").strip() or f"{self.user + '@' if self.user else ''}{host}",
        )

    def to_dict(self) -> dict[str, object]:
        """JSON-safe mapping (never includes secrets)."""
        return asdict(self.normalized())


@dataclass(frozen=True)
class RemoteProjectBinding:
    """Maps a local cache directory to a remote project root."""

    profile_id: str
    host: str
    port: int
    user: str
    auth: str
    identity_file: str
    remote_root: str
    remote_cdm3: str
    local_root: str
    local_cdm3: str

    def to_dict(self) -> dict[str, str]:
        """JSON-safe mapping."""
        return {k: str(v) for k, v in asdict(self).items()}


@runtime_checkable
class SftpSession(Protocol):
    """Minimal SFTP surface for remote project sync."""

    def listdir(self, path: str) -> list[str]:
        """List entry names (not including ``.`` / ``..``)."""

    def isdir(self, path: str) -> bool:
        """True when ``path`` is a directory."""

    def isfile(self, path: str) -> bool:
        """True when ``path`` is a regular file."""

    def mkdir(self, path: str, *, mode: int = 0o755) -> None:
        """Create a directory (parents not required for Fake; Paramiko may need parents)."""

    def makedirs(self, path: str, *, mode: int = 0o755) -> None:
        """Create ``path`` and parents."""

    def read_bytes(self, path: str) -> bytes:
        """Read an entire file."""

    def write_bytes(self, path: str, data: bytes) -> None:
        """Write/replace an entire file."""

    def close(self) -> None:
        """Release the session."""


class FakeSftpSession:
    """In-memory SFTP for contract tests (POSIX paths)."""

    def __init__(self, tree: Optional[Mapping[str, object]] = None) -> None:
        # path -> bytes for files; directories implied by prefixes.
        self.files: dict[str, bytes] = {}
        self.dirs: set[str] = {"/"}
        if tree:
            self._ingest("", tree)

    def _ingest(self, prefix: str, node: Mapping[str, object] | object) -> None:
        if isinstance(node, Mapping):
            path = prefix or "/"
            self.dirs.add(_norm_remote(path))
            for name, child in node.items():
                child_path = posixpath.join(path if path != "/" else "", name)
                if isinstance(child, (bytes, bytearray)):
                    self.files[_norm_remote(child_path)] = bytes(child)
                    self.dirs.add(_norm_remote(posixpath.dirname(child_path) or "/"))
                elif isinstance(child, str):
                    self.files[_norm_remote(child_path)] = child.encode("utf-8")
                    self.dirs.add(_norm_remote(posixpath.dirname(child_path) or "/"))
                else:
                    self._ingest(child_path, child)
        else:
            raise TypeError("FakeSftpSession tree leaves must be str/bytes or nested mappings")

    def listdir(self, path: str) -> list[str]:
        path = _norm_remote(path)
        if not self.isdir(path):
            raise FileNotFoundError(path)
        prefix = "" if path == "/" else path.strip("/") + "/"
        names: set[str] = set()
        for d in self.dirs:
            if d == "/" or d == path:
                continue
            rel = d.lstrip("/")
            if prefix and not rel.startswith(prefix):
                continue
            rest = rel[len(prefix) :] if prefix else rel
            if rest and "/" not in rest:
                names.add(rest)
        for f in self.files:
            rel = f.lstrip("/")
            if prefix and not rel.startswith(prefix):
                continue
            rest = rel[len(prefix) :] if prefix else rel
            if rest and "/" not in rest:
                names.add(rest)
        return sorted(names)

    def isdir(self, path: str) -> bool:
        return _norm_remote(path) in self.dirs

    def isfile(self, path: str) -> bool:
        return _norm_remote(path) in self.files

    def mkdir(self, path: str, *, mode: int = 0o755) -> None:
        del mode
        path = _norm_remote(path)
        parent = _norm_remote(posixpath.dirname(path) or "/")
        if parent != "/" and parent not in self.dirs:
            raise FileNotFoundError(parent)
        self.dirs.add(path)

    def makedirs(self, path: str, *, mode: int = 0o755) -> None:
        path = _norm_remote(path)
        parts = [p for p in path.split("/") if p]
        cur = "/"
        for part in parts:
            cur = posixpath.join(cur, part)
            if cur not in self.dirs:
                self.mkdir(cur, mode=mode)

    def read_bytes(self, path: str) -> bytes:
        path = _norm_remote(path)
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def write_bytes(self, path: str, data: bytes) -> None:
        path = _norm_remote(path)
        parent = _norm_remote(posixpath.dirname(path) or "/")
        if parent not in self.dirs:
            self.makedirs(parent)
        self.files[path] = data

    def close(self) -> None:
        return None


class ParamikoSftpSession:
    """SFTP session backed by Paramiko."""

    def __init__(self, client) -> None:
        self._client = client
        self._sftp = client.open_sftp()

    def listdir(self, path: str) -> list[str]:
        return sorted(self._sftp.listdir(_norm_remote(path)))

    def isdir(self, path: str) -> bool:
        import stat as statmod

        try:
            return statmod.S_ISDIR(self._sftp.stat(_norm_remote(path)).st_mode)
        except OSError:
            return False

    def isfile(self, path: str) -> bool:
        import stat as statmod

        try:
            return statmod.S_ISREG(self._sftp.stat(_norm_remote(path)).st_mode)
        except OSError:
            return False

    def mkdir(self, path: str, *, mode: int = 0o755) -> None:
        self._sftp.mkdir(_norm_remote(path), mode=mode)

    def makedirs(self, path: str, *, mode: int = 0o755) -> None:
        path = _norm_remote(path)
        parts = [p for p in path.split("/") if p]
        cur = "/"
        for part in parts:
            cur = posixpath.join(cur, part)
            if not self.isdir(cur):
                try:
                    self.mkdir(cur, mode=mode)
                except OSError:
                    if not self.isdir(cur):
                        raise

    def read_bytes(self, path: str) -> bytes:
        with self._sftp.open(_norm_remote(path), "rb") as handle:
            return handle.read()

    def write_bytes(self, path: str, data: bytes) -> None:
        path = _norm_remote(path)
        parent = _norm_remote(posixpath.dirname(path) or "/")
        if parent != "/" and not self.isdir(parent):
            self.makedirs(parent)
        with self._sftp.open(path, "wb") as handle:
            handle.write(data)

    def close(self) -> None:
        try:
            self._sftp.close()
        finally:
            self._client.close()


def require_paramiko():
    """Import paramiko or raise a clear error."""
    try:
        import paramiko  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "SSH remote projects require the 'paramiko' package. "
            "Install with: pip install 'paramiko>=3.0'  (or: pip install -e '.[ssh]')"
        ) from exc
    return paramiko


def connect_paramiko_sftp(
    profile: SshHostProfile,
    *,
    password: str = "",
) -> ParamikoSftpSession:
    """Open a live SFTP session for ``profile``."""
    paramiko = require_paramiko()
    cfg = profile.normalized()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs: dict[str, object] = {
        "hostname": cfg.host,
        "port": cfg.port,
        "username": cfg.user or None,
        "allow_agent": True,
        "look_for_keys": True,
        "timeout": 30,
    }
    if cfg.auth == "password":
        if not password:
            raise ValueError("password auth selected but password is empty")
        kwargs["password"] = password
        kwargs["look_for_keys"] = False
        kwargs["allow_agent"] = False
    elif cfg.identity_file:
        kwargs["key_filename"] = cfg.identity_file
    client.connect(**kwargs)
    return ParamikoSftpSession(client)


def hosts_path(settings_dir: Optional[str] = None) -> str:
    """Path to the host profiles JSON file."""
    base = settings_dir or SETTINGS_DIR
    return os.path.join(base, HOSTS_FILENAME)


def load_host_profiles(settings_dir: Optional[str] = None) -> list[SshHostProfile]:
    """Load saved host profiles (empty list if missing/corrupt)."""
    path = hosts_path(settings_dir)
    if not os.path.isfile(path):
        return []
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logging.warning("Could not read SSH host profiles: %s", exc)
        return []
    items = raw.get("hosts", []) if isinstance(raw, dict) else []
    out: list[SshHostProfile] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            out.append(
                SshHostProfile(
                    id=str(item.get("id", "")),
                    host=str(item.get("host", "")),
                    port=int(item.get("port", 22) or 22),
                    user=str(item.get("user", "")),
                    auth=str(item.get("auth", "key")),
                    identity_file=str(item.get("identity_file", "")),
                    label=str(item.get("label", "")),
                ).normalized()
            )
        except (TypeError, ValueError) as exc:
            logging.warning("Skipping invalid SSH host profile: %s", exc)
    return out


def save_host_profiles(profiles: Sequence[SshHostProfile], settings_dir: Optional[str] = None) -> None:
    """Persist non-secret host profiles."""
    path = hosts_path(settings_dir)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {"hosts": [p.normalized().to_dict() for p in profiles]}
    atomic_write_text(path, json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def upsert_host_profile(profile: SshHostProfile, settings_dir: Optional[str] = None) -> SshHostProfile:
    """Insert or replace a profile by id and save."""
    cfg = profile.normalized()
    existing = [p for p in load_host_profiles(settings_dir) if p.id != cfg.id]
    existing.append(cfg)
    existing.sort(key=lambda p: p.label.lower())
    save_host_profiles(existing, settings_dir)
    return cfg


def password_file_path(profile_id: str, settings_dir: Optional[str] = None) -> str:
    """Fallback password file path (mode 0600)."""
    base = settings_dir or SETTINGS_DIR
    safe = _SAFE_ID.sub("_", profile_id)[:80]
    return os.path.join(base, f"ssh_password_{safe}")


def store_ssh_password(profile_id: str, password: str, settings_dir: Optional[str] = None) -> None:
    """Store password in keyring or a 0600 file."""
    if not profile_id:
        raise ValueError("profile_id required")
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, profile_id, password or "")
        return
    except Exception:
        pass
    path = password_file_path(profile_id, settings_dir)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".ssh-pass-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(password or "")
        os.chmod(tmp, TOKEN_FILE_MODE)
        os.replace(tmp, path)
        os.chmod(path, TOKEN_FILE_MODE)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def load_ssh_password(profile_id: str, settings_dir: Optional[str] = None) -> str:
    """Load password from keyring or fallback file."""
    if not profile_id:
        return ""
    try:
        import keyring

        value = keyring.get_password(KEYRING_SERVICE, profile_id)
        if value is not None:
            return value
    except Exception:
        pass
    path = password_file_path(profile_id, settings_dir)
    if not os.path.isfile(path):
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def remote_cache_dir(profile: SshHostProfile, remote_root: str, settings_dir: Optional[str] = None) -> str:
    """Deterministic local cache directory for a remote project root."""
    cfg = profile.normalized()
    digest = hashlib.sha256(f"{cfg.id}:{_norm_remote(remote_root)}".encode("utf-8")).hexdigest()[:16]
    base = settings_dir or SETTINGS_DIR
    return os.path.join(base, "remote-projects", cfg.id, digest)


def find_remote_cdm3(session: SftpSession, remote_path: str) -> str:
    """Resolve a remote ``.cdm3`` path from a file or directory."""
    path = _norm_remote(remote_path)
    if session.isfile(path):
        if not path.lower().endswith(".cdm3"):
            raise ValueError(f"remote path is not a .cdm3 project file: {path}")
        return path
    if not session.isdir(path):
        raise FileNotFoundError(f"remote path not found: {path}")
    names = [n for n in session.listdir(path) if n.lower().endswith(".cdm3")]
    if not names:
        raise FileNotFoundError(f"no .cdm3 project file in remote directory: {path}")
    names.sort()
    return _norm_remote(posixpath.join(path, names[0]))


def download_remote_tree(
    session: SftpSession,
    remote_root: str,
    local_root: str,
    *,
    max_files: int = MAX_REMOTE_FILES,
    max_bytes: int = MAX_REMOTE_BYTES,
) -> int:
    """Recursively download ``remote_root`` into ``local_root``. Return file count."""
    remote_root = _norm_remote(remote_root)
    os.makedirs(local_root, exist_ok=True)
    count = 0
    total = 0
    stack = [remote_root]
    while stack:
        current = stack.pop()
        for name in session.listdir(current):
            if name in SKIP_DIR_NAMES or name in (".", ".."):
                continue
            remote_item = _norm_remote(posixpath.join(current, name))
            rel = remote_item[len(remote_root) :].lstrip("/") if remote_item != remote_root else ""
            local_item = os.path.join(local_root, *rel.split("/")) if rel else local_root
            if session.isdir(remote_item):
                os.makedirs(local_item, exist_ok=True)
                stack.append(remote_item)
                continue
            if not session.isfile(remote_item):
                continue
            data = session.read_bytes(remote_item)
            total += len(data)
            if total > max_bytes:
                raise RuntimeError(f"remote project exceeds download size limit ({max_bytes} bytes)")
            count += 1
            if count > max_files:
                raise RuntimeError(f"remote project exceeds file count limit ({max_files})")
            os.makedirs(os.path.dirname(local_item) or ".", exist_ok=True)
            Path(local_item).write_bytes(data)
    return count


def upload_file(session: SftpSession, local_path: str, remote_path: str) -> None:
    """Upload one local file to ``remote_path``."""
    data = Path(local_path).read_bytes()
    session.write_bytes(_norm_remote(remote_path), data)


def write_binding(binding: RemoteProjectBinding) -> None:
    """Persist binding next to the local cache root."""
    path = os.path.join(binding.local_root, BINDING_FILENAME)
    atomic_write_text(path, json.dumps(binding.to_dict(), indent=2) + "\n", encoding="utf-8")


def read_binding(local_root: str) -> Optional[RemoteProjectBinding]:
    """Load binding from a local cache directory."""
    path = os.path.join(local_root, BINDING_FILENAME)
    if not os.path.isfile(path):
        return None
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return RemoteProjectBinding(
            profile_id=str(raw["profile_id"]),
            host=str(raw["host"]),
            port=int(raw["port"]),
            user=str(raw.get("user", "")),
            auth=str(raw.get("auth", "key")),
            identity_file=str(raw.get("identity_file", "")),
            remote_root=str(raw["remote_root"]),
            remote_cdm3=str(raw["remote_cdm3"]),
            local_root=str(raw["local_root"]),
            local_cdm3=str(raw["local_cdm3"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def open_remote_project(
    session: SftpSession,
    profile: SshHostProfile,
    remote_path: str,
    *,
    settings_dir: Optional[str] = None,
) -> RemoteProjectBinding:
    """Download a remote project into the local cache and return the binding."""
    cfg = profile.normalized()
    remote_cdm3 = find_remote_cdm3(session, remote_path)
    remote_root = _norm_remote(posixpath.dirname(remote_cdm3) or "/")
    local_root = remote_cache_dir(cfg, remote_root, settings_dir)
    if os.path.isdir(local_root):
        # Fresh sync: clear previous tree except we recreate.
        _rm_tree(local_root)
    os.makedirs(local_root, exist_ok=True)
    download_remote_tree(session, remote_root, local_root)
    local_cdm3 = os.path.join(local_root, os.path.basename(remote_cdm3))
    if not os.path.isfile(local_cdm3):
        raise FileNotFoundError(f"downloaded tree is missing project file: {local_cdm3}")
    binding = RemoteProjectBinding(
        profile_id=cfg.id,
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        auth=cfg.auth,
        identity_file=cfg.identity_file,
        remote_root=remote_root,
        remote_cdm3=remote_cdm3,
        local_root=local_root,
        local_cdm3=local_cdm3,
    )
    write_binding(binding)
    return binding


def create_remote_project(
    session: SftpSession,
    profile: SshHostProfile,
    remote_parent: str,
    project_name: str,
    *,
    cdm3_body: str,
    settings_dir: Optional[str] = None,
) -> RemoteProjectBinding:
    """Create remote dir + ``.cdm3``, seed local cache, return binding."""
    cfg = profile.normalized()
    name = (project_name or "").strip()
    if not name:
        raise ValueError("project name required")
    if name.endswith(".cdm3"):
        name = name[: -len(".cdm3")]
    parent = _norm_remote(remote_parent)
    remote_root = _norm_remote(posixpath.join(parent, name))
    remote_cdm3 = _norm_remote(posixpath.join(remote_root, f"{name}.cdm3"))
    if session.isdir(remote_root) or session.isfile(remote_root):
        raise FileExistsError(f"remote path already exists: {remote_root}")
    session.makedirs(remote_root)
    session.write_bytes(remote_cdm3, cdm3_body.encode("utf-8"))
    local_root = remote_cache_dir(cfg, remote_root, settings_dir)
    if os.path.isdir(local_root):
        _rm_tree(local_root)
    os.makedirs(local_root, exist_ok=True)
    local_cdm3 = os.path.join(local_root, f"{name}.cdm3")
    Path(local_cdm3).write_text(cdm3_body, encoding="utf-8")
    binding = RemoteProjectBinding(
        profile_id=cfg.id,
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        auth=cfg.auth,
        identity_file=cfg.identity_file,
        remote_root=remote_root,
        remote_cdm3=remote_cdm3,
        local_root=local_root,
        local_cdm3=local_cdm3,
    )
    write_binding(binding)
    return binding


def default_cdm3_json(project_name: str) -> str:
    """Minimal valid ``.cdm3`` body for a new remote project."""
    from utils.project import merge_project_defaults, new_project_uuid
    from utils.project_schema import validate_project_props

    props = merge_project_defaults(
        validate_project_props(
            {
                "uuid": new_project_uuid(),
                "scriptname": "",
                "description": f"Remote SSH project {project_name}",
            }
        )
    )
    return json.dumps(props, indent=4) + "\n"


def _make_profile_id(host: str, user: str, port: int) -> str:
    raw = f"{user or 'user'}@{host}:{port}"
    return _SAFE_ID.sub("-", raw).strip("-").lower()[:80]


def _norm_remote(path: str) -> str:
    text = (path or "").replace("\\", "/").strip()
    if not text:
        return "/"
    if text == "/":
        return "/"
    # Keep absolute POSIX form for SFTP.
    if not text.startswith("/"):
        text = "/" + text
    return posixpath.normpath(text)


def _rm_tree(path: str) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)


__all__ = [
    "FakeSftpSession",
    "ParamikoSftpSession",
    "RemoteProjectBinding",
    "SftpSession",
    "SshHostProfile",
    "connect_paramiko_sftp",
    "create_remote_project",
    "default_cdm3_json",
    "download_remote_tree",
    "find_remote_cdm3",
    "load_host_profiles",
    "load_ssh_password",
    "open_remote_project",
    "read_binding",
    "require_paramiko",
    "save_host_profiles",
    "store_ssh_password",
    "upload_file",
    "upsert_host_profile",
    "write_binding",
]
