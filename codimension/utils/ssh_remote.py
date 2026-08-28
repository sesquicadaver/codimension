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

R183: ``profile.id`` and remote project names are basename allowlists only;
local cache mkdir/rmtree/write is constrained with ``realpath``/``commonpath``.

R184: SSH host authenticity — ``RejectPolicy`` by default, load known_hosts,
optional TOFU only after explicit trust, pin ``host_key_fingerprint`` in the
profile; fingerprint mismatch fails closed.

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
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable

from utils.atomic_io import atomic_write_text
from utils.settings import SETTINGS_DIR

HOSTS_FILENAME = "ssh_hosts.json"
BINDING_FILENAME = "binding.json"
KNOWN_HOSTS_FILENAME = "ssh_known_hosts"
KEYRING_SERVICE = "codimension-ssh"
TOKEN_FILE_MODE = 0o600

# Optional safety caps: 0 means unlimited (default). Override via kwargs or
# env ``CDM_SSH_MAX_FILES`` / ``CDM_SSH_MAX_BYTES`` (positive integers).
MAX_REMOTE_FILES = 0
MAX_REMOTE_BYTES = 0
ENV_MAX_FILES = "CDM_SSH_MAX_FILES"
ENV_MAX_BYTES = "CDM_SSH_MAX_BYTES"
SKIP_DIR_NAMES = frozenset({".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules"})

# R183: path-containment — profile ids and project names are basename-only allowlists.
_SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")
_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


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
    # R184: OpenSSH-style ``SHA256:…`` pin of the remote host key (empty = unset).
    host_key_fingerprint: str = ""

    def normalized(self) -> "SshHostProfile":
        """Validate and normalize fields (R183: profile id is basename-safe)."""
        host = (self.host or "").strip()
        if not host:
            raise ValueError("host must be non-empty")
        auth = (self.auth or "key").strip().lower()
        if auth not in ("key", "password"):
            raise ValueError("auth must be 'key' or 'password'")
        port = int(self.port or 22)
        if port < 1 or port > 65535:
            raise ValueError("port out of range")
        raw_id = (self.id or "").strip()
        if raw_id:
            pid = sanitize_ssh_profile_id(raw_id)
        else:
            pid = sanitize_ssh_profile_id(_make_profile_id(host, self.user, port))
        fp = normalize_host_key_fingerprint(self.host_key_fingerprint)
        return SshHostProfile(
            id=pid,
            host=host,
            port=port,
            user=(self.user or "").strip(),
            auth=auth,
            identity_file=os.path.expanduser((self.identity_file or "").strip()),
            label=(self.label or "").strip() or f"{self.user + '@' if self.user else ''}{host}",
            host_key_fingerprint=fp,
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

    def __init__(self, client, profile: Optional[SshHostProfile] = None) -> None:
        self._client = client
        self.profile = profile
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
            return bytes(handle.read())

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
            "Install with: pip install 'paramiko>=3.0'  (or re-run: ./scripts/codimension_ctl.sh install --yes)"
        ) from exc
    return paramiko


class UnknownHostKeyError(RuntimeError):
    """Raised when the remote host key is not in known_hosts and TOFU was not granted."""

    def __init__(self, hostname: str, fingerprint: str, key_type: str = "") -> None:
        self.hostname = hostname
        self.fingerprint = fingerprint
        self.key_type = key_type
        detail = f"Unknown SSH host key for {hostname}: {fingerprint}"
        if key_type:
            detail += f" ({key_type})"
        detail += ". Confirm the fingerprint (TOFU) or add the host to known_hosts."
        super().__init__(detail)


class HostKeyFingerprintMismatch(RuntimeError):
    """Raised when the live host key does not match the profile pin (fail closed)."""

    def __init__(self, hostname: str, expected: str, actual: str) -> None:
        self.hostname = hostname
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"SSH host key mismatch for {hostname}: expected {expected}, got {actual}. "
            "Connection refused (possible MITM)."
        )


def normalize_host_key_fingerprint(raw: str) -> str:
    """Normalize an OpenSSH-style fingerprint to ``SHA256:…`` (no trailing ``=``)."""
    text = (raw or "").strip()
    if not text:
        return ""
    if text.lower().startswith("sha256:"):
        body = text.split(":", 1)[1].strip().rstrip("=")
        if not body:
            raise ValueError("empty host key fingerprint")
        return "SHA256:" + body
    # Accept bare base64 body.
    body = text.rstrip("=")
    if not re.fullmatch(r"[A-Za-z0-9+/]+", body):
        raise ValueError("invalid host key fingerprint")
    return "SHA256:" + body


def ssh_host_key_fingerprint(key: Any) -> str:
    """Return OpenSSH ``SHA256:…`` fingerprint for a Paramiko PKey."""
    import base64

    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def known_hosts_paths(settings_dir: Optional[str] = None) -> list[str]:
    """Ordered known_hosts files to load (existing paths only)."""
    paths: list[str] = []
    user_kh = os.path.expanduser(os.path.join("~", ".ssh", "known_hosts"))
    paths.append(user_kh)
    base = _settings_base(settings_dir)
    paths.append(os.path.join(base, KNOWN_HOSTS_FILENAME))
    return [p for p in paths if os.path.isfile(p)]


def load_ssh_client_host_keys(client: Any, settings_dir: Optional[str] = None) -> None:
    """Load system + user + Codimension known_hosts into ``client``."""
    try:
        client.load_system_host_keys()
    except Exception as exc:
        logging.debug("load_system_host_keys skipped: %s", exc)
    for path in known_hosts_paths(settings_dir):
        try:
            client.load_host_keys(path)
        except Exception as exc:
            logging.warning("Could not load known_hosts %s: %s", path, exc)


def _reject_missing_host_key_policy(paramiko_mod: Any) -> Any:
    """MissingHostKeyPolicy that raises :class:`UnknownHostKeyError` (R184)."""

    class _Reject(paramiko_mod.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):  # noqa: ANN001
            del client
            raise UnknownHostKeyError(hostname, ssh_host_key_fingerprint(key), key.get_name())

    return _Reject()


def _trust_once_host_key_policy(paramiko_mod: Any) -> Any:
    """Accept one unknown host key into the in-memory host key store (TOFU)."""

    class _TrustOnce(paramiko_mod.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):  # noqa: ANN001
            client.get_host_keys().add(hostname, key.get_name(), key)
            logging.info(
                "TOFU: accepted SSH host key for %s (%s)",
                hostname,
                ssh_host_key_fingerprint(key),
            )

    return _TrustOnce()


def verify_remote_host_key_fingerprint(client: Any, expected: str, *, hostname: str) -> str:
    """Fail closed when the live server key fingerprint ≠ ``expected`` pin."""
    transport = client.get_transport()
    if transport is None:
        raise RuntimeError("SSH transport missing after connect")
    key = transport.get_remote_server_key()
    actual = ssh_host_key_fingerprint(key)
    exp = normalize_host_key_fingerprint(expected)
    if actual != exp:
        raise HostKeyFingerprintMismatch(hostname, exp, actual)
    return actual


def open_paramiko_ssh_client(
    profile: SshHostProfile,
    *,
    password: str = "",
    trust_unknown_host: bool = False,
    settings_dir: Optional[str] = None,
) -> tuple[Any, SshHostProfile]:
    """Connect an ``SSHClient`` with R184 host-key policy.

    Returns ``(client, profile)`` where ``profile`` may gain a new
    ``host_key_fingerprint`` pin when TOFU was granted.
    """
    paramiko = require_paramiko()
    cfg = profile.normalized()
    client = paramiko.SSHClient()
    load_ssh_client_host_keys(client, settings_dir)
    if cfg.host_key_fingerprint or trust_unknown_host:
        # Pin present: allow handshake then verify fingerprint (fail closed).
        # TOFU without pin: accept once after explicit caller consent.
        client.set_missing_host_key_policy(_trust_once_host_key_policy(paramiko))
    else:
        client.set_missing_host_key_policy(_reject_missing_host_key_policy(paramiko))
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
    transport = client.get_transport()
    if transport is None:
        client.close()
        raise RuntimeError("SSH transport missing after connect")
    actual = ssh_host_key_fingerprint(transport.get_remote_server_key())
    if cfg.host_key_fingerprint:
        if actual != cfg.host_key_fingerprint:
            client.close()
            raise HostKeyFingerprintMismatch(cfg.host, cfg.host_key_fingerprint, actual)
        return client, cfg
    if trust_unknown_host:
        pinned = replace(cfg, host_key_fingerprint=actual)
        return client, pinned
    # Connected via known_hosts without a profile pin — pin now for next time.
    return client, replace(cfg, host_key_fingerprint=actual)


def connect_paramiko_sftp(
    profile: SshHostProfile,
    *,
    password: str = "",
    trust_unknown_host: bool = False,
    settings_dir: Optional[str] = None,
) -> ParamikoSftpSession:
    """Open a live SFTP session for ``profile`` (R184 host-key verification)."""
    client, pinned = open_paramiko_ssh_client(
        profile,
        password=password,
        trust_unknown_host=trust_unknown_host,
        settings_dir=settings_dir,
    )
    return ParamikoSftpSession(client, pinned)


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
                    host_key_fingerprint=str(item.get("host_key_fingerprint", "")),
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
    base = _settings_base(settings_dir)
    safe = sanitize_ssh_profile_id(profile_id)
    return os.path.join(base, f"ssh_password_{safe}")


def store_ssh_password(profile_id: str, password: str, settings_dir: Optional[str] = None) -> None:
    """Store password in keyring or a 0600 file."""
    safe_id = sanitize_ssh_profile_id(profile_id)
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, safe_id, password or "")
        return
    except Exception:
        pass
    path = password_file_path(safe_id, settings_dir)
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
        safe_id = sanitize_ssh_profile_id(profile_id)
    except ValueError:
        return ""
    try:
        import keyring

        value = keyring.get_password(KEYRING_SERVICE, safe_id)
        if value is not None:
            return str(value)
    except Exception:
        pass
    path = password_file_path(safe_id, settings_dir)
    if not os.path.isfile(path):
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def remote_projects_root(settings_dir: Optional[str] = None) -> str:
    """Absolute root of local remote-project caches (R183 container)."""
    return os.path.join(_settings_base(settings_dir), "remote-projects")


def remote_cache_dir(profile: SshHostProfile, remote_root: str, settings_dir: Optional[str] = None) -> str:
    """Deterministic local cache directory for a remote project root.

    Always under ``<settings>/remote-projects/<safe-id>/<digest>/`` (R183).
    """
    cfg = profile.normalized()
    digest = hashlib.sha256(f"{cfg.id}:{_norm_remote(remote_root)}".encode("utf-8")).hexdigest()[:16]
    cache_root = remote_projects_root(settings_dir)
    candidate = os.path.join(cache_root, cfg.id, digest)
    return assert_local_path_under(cache_root, candidate)


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


def resolve_download_limits(
    *,
    max_files: Optional[int] = None,
    max_bytes: Optional[int] = None,
) -> tuple[int, int]:
    """Return ``(max_files, max_bytes)``; ``0`` means unlimited.

    Explicit kwargs win; otherwise read ``CDM_SSH_MAX_FILES`` /
    ``CDM_SSH_MAX_BYTES``; otherwise module defaults (unlimited).
    """
    files = MAX_REMOTE_FILES if max_files is None else int(max_files)
    size = MAX_REMOTE_BYTES if max_bytes is None else int(max_bytes)
    if max_files is None:
        raw = os.environ.get(ENV_MAX_FILES, "").strip()
        if raw:
            files = max(0, int(raw))
    if max_bytes is None:
        raw = os.environ.get(ENV_MAX_BYTES, "").strip()
        if raw:
            size = max(0, int(raw))
    return max(0, files), max(0, size)


def download_remote_tree(
    session: SftpSession,
    remote_root: str,
    local_root: str,
    *,
    max_files: Optional[int] = None,
    max_bytes: Optional[int] = None,
) -> int:
    """Recursively download ``remote_root`` into ``local_root``. Return file count.

    By default there is **no** file-count or byte-size cap (large projects are
    supported). Pass positive ``max_files`` / ``max_bytes``, or set
    ``CDM_SSH_MAX_FILES`` / ``CDM_SSH_MAX_BYTES``, to enforce an optional safety stop.
    """
    limit_files, limit_bytes = resolve_download_limits(max_files=max_files, max_bytes=max_bytes)
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
            if limit_bytes > 0 and total > limit_bytes:
                raise RuntimeError(f"remote project exceeds download size limit ({limit_bytes} bytes)")
            count += 1
            if limit_files > 0 and count > limit_files:
                raise RuntimeError(f"remote project exceeds file count limit ({limit_files})")
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
    cache_root = remote_projects_root(settings_dir)
    local_root = remote_cache_dir(cfg, remote_root, settings_dir)
    if os.path.isdir(local_root):
        # Fresh sync: clear previous tree except we recreate.
        _rm_tree(local_root, must_be_under=cache_root)
    os.makedirs(local_root, exist_ok=True)
    download_remote_tree(session, remote_root, local_root)
    local_cdm3 = assert_local_path_under(local_root, os.path.join(local_root, os.path.basename(remote_cdm3)))
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
    name = sanitize_remote_project_name(project_name)
    parent = _norm_remote(remote_parent)
    remote_root = assert_remote_path_under(parent, _norm_remote(posixpath.join(parent, name)))
    remote_cdm3 = assert_remote_path_under(remote_root, _norm_remote(posixpath.join(remote_root, f"{name}.cdm3")))
    if session.isdir(remote_root) or session.isfile(remote_root):
        raise FileExistsError(f"remote path already exists: {remote_root}")
    session.makedirs(remote_root)
    session.write_bytes(remote_cdm3, cdm3_body.encode("utf-8"))
    cache_root = remote_projects_root(settings_dir)
    local_root = remote_cache_dir(cfg, remote_root, settings_dir)
    if os.path.isdir(local_root):
        _rm_tree(local_root, must_be_under=cache_root)
    os.makedirs(local_root, exist_ok=True)
    local_cdm3 = assert_local_path_under(local_root, os.path.join(local_root, f"{name}.cdm3"))
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


def default_cdm3_json(project_name: str, extra: Optional[Mapping[str, object]] = None) -> str:
    """Minimal valid ``.cdm3`` body for a new remote project."""
    props: dict[str, object] = {
        "uuid": "",
        "scriptname": "",
        "description": f"Remote SSH project {project_name}",
    }
    if extra:
        props.update(dict(extra))
    return cdm3_json_from_props(props)


def cdm3_json_from_props(props: Mapping[str, object]) -> str:
    """Build a validated ``.cdm3`` JSON document from property mapping."""
    from utils.project import merge_project_defaults, new_project_uuid
    from utils.project_schema import validate_project_props

    data = dict(props)
    if not str(data.get("uuid") or "").strip():
        data["uuid"] = new_project_uuid()
    merged = merge_project_defaults(validate_project_props(data))
    return json.dumps(merged, indent=4) + "\n"


def remote_relpath(project_root: str, remote_path: str) -> str:
    """Return path relative to ``project_root`` when possible (POSIX)."""
    root = _norm_remote(project_root)
    path = _norm_remote(remote_path)
    if path == root:
        return "."
    prefix = root if root.endswith("/") else root + "/"
    if path.startswith(prefix):
        return path[len(prefix) :]
    return path


def sanitize_ssh_profile_id(raw: str) -> str:
    """Return a basename-safe profile id or raise ``ValueError`` (R183).

    Rejects absolute paths, separators, ``.`` / ``..``, and any character
    outside ``[A-Za-z0-9._-]``. Empty input is rejected (callers generate ids).
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("profile id required")
    if text in (".", "..") or "/" in text or "\\" in text or os.path.isabs(text):
        raise ValueError("invalid profile id: path components are not allowed")
    if os.sep in text or (os.altsep and os.altsep in text):
        raise ValueError("invalid profile id: path separators are not allowed")
    if not _PROFILE_ID_RE.fullmatch(text):
        raise ValueError(
            "invalid profile id: use letters, digits, '.', '_' or '-' (1–80 chars, must start with alphanumeric)"
        )
    return text


def sanitize_remote_project_name(raw: str) -> str:
    """Return a basename-safe project name or raise ``ValueError`` (R183)."""
    name = (raw or "").strip()
    if name.lower().endswith(".cdm3"):
        name = name[: -len(".cdm3")].rstrip()
    if not name:
        raise ValueError("project name required")
    if name in (".", "..") or "/" in name or "\\" in name or os.path.isabs(name):
        raise ValueError("invalid project name: path components are not allowed")
    if os.sep in name or (os.altsep and os.altsep in name):
        raise ValueError("invalid project name: path separators are not allowed")
    if not _PROJECT_NAME_RE.fullmatch(name):
        raise ValueError(
            "invalid project name: use letters, digits, '.', '_' or '-' (1–128 chars, must start with alphanumeric)"
        )
    return name


def assert_remote_path_under(parent: str, child: str) -> str:
    """Ensure POSIX ``child`` is ``parent`` or a strict descendant (R183)."""
    parent_n = _norm_remote(parent)
    child_n = _norm_remote(child)
    if child_n == parent_n:
        return child_n
    prefix = parent_n if parent_n.endswith("/") else parent_n + "/"
    if not child_n.startswith(prefix):
        raise ValueError(f"remote path escapes parent {parent_n!r}: {child_n}")
    return child_n


def assert_local_path_under(root: str, path: str) -> str:
    """Ensure local ``path`` stays under ``root`` via ``commonpath`` (R183)."""
    root_norm = os.path.normpath(os.path.abspath(root))
    path_norm = os.path.normpath(os.path.abspath(path))
    try:
        common = os.path.commonpath([root_norm, path_norm])
    except ValueError as exc:
        raise ValueError(f"local path escapes container {root_norm!r}: {path_norm}") from exc
    if common != root_norm:
        raise ValueError(f"local path escapes container {root_norm!r}: {path_norm}")
    return path_norm


def _settings_base(settings_dir: Optional[str] = None) -> str:
    """Absolute settings directory (may not exist yet)."""
    return os.path.abspath(settings_dir or SETTINGS_DIR)


def _make_profile_id(host: str, user: str, port: int) -> str:
    raw = f"{user or 'user'}@{host}:{port}"
    cleaned = _SAFE_ID.sub("-", raw).strip("-").lower()[:80]
    if not cleaned or not cleaned[0].isalnum():
        cleaned = "h" + (cleaned or "ost")
        cleaned = cleaned[:80]
    # Ensure allowlist match after generation.
    if not _PROFILE_ID_RE.fullmatch(cleaned):
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        cleaned = f"host-{digest}"
    return cleaned


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


def _rm_tree(path: str, *, must_be_under: str) -> None:
    """Remove a directory tree only when it is contained under ``must_be_under``."""
    import shutil

    target = assert_local_path_under(must_be_under, path)
    # Extra guard: never delete the container root itself.
    container = os.path.normpath(os.path.abspath(must_be_under))
    if target == container:
        raise ValueError(f"refusing to remove cache container root: {target}")
    shutil.rmtree(target, ignore_errors=True)


__all__ = [
    "FakeSftpSession",
    "HostKeyFingerprintMismatch",
    "ParamikoSftpSession",
    "RemoteProjectBinding",
    "SftpSession",
    "SshHostProfile",
    "UnknownHostKeyError",
    "assert_local_path_under",
    "assert_remote_path_under",
    "connect_paramiko_sftp",
    "create_remote_project",
    "cdm3_json_from_props",
    "default_cdm3_json",
    "download_remote_tree",
    "find_remote_cdm3",
    "known_hosts_paths",
    "load_host_profiles",
    "load_ssh_client_host_keys",
    "load_ssh_password",
    "normalize_host_key_fingerprint",
    "open_paramiko_ssh_client",
    "open_remote_project",
    "read_binding",
    "remote_cache_dir",
    "remote_projects_root",
    "remote_relpath",
    "require_paramiko",
    "resolve_download_limits",
    "sanitize_remote_project_name",
    "sanitize_ssh_profile_id",
    "save_host_profiles",
    "ssh_host_key_fingerprint",
    "store_ssh_password",
    "upload_file",
    "upsert_host_profile",
    "verify_remote_host_key_fingerprint",
    "write_binding",
]
