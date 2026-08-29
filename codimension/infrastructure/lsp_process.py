# -*- coding: utf-8 -*-
#
# codimension - LSP stdio JSON-RPC process client (R202)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""LspProcess: one language-server subprocess per process key (R202).

Key: ``(language_id, workspace_root, toolchain)``. Spawn is gated by
:func:`core.language_policy.require_language_server_spawn` (absolute binary on
allowlist only). Transport: JSON-RPC over stdio with Content-Length framing,
reader thread, serialized writer, cancel, timeouts, bounded stderr ring,
bounded message size, lazy start, bounded backoff restart, and
initialize → shutdown → exit on unload.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

from core.language_policy import LanguageServerSpawnError, require_language_server_spawn
from infrastructure.lsp_framing import (
    DEFAULT_MAX_MESSAGE_BYTES,
    LspFramingError,
    encode_message,
    read_message,
)
from infrastructure.lsp_position_codec import LspPositionCodec, LspPositionEncoding

PopenFactory = Callable[..., subprocess.Popen]


class LspProcessState(str, Enum):
    """Lifecycle state for :class:`LspProcess`."""

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class LspProtocolError(RuntimeError):
    """JSON-RPC / LSP protocol failure (error response or transport)."""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        data: Any = None,
    ) -> None:
        self.code = code
        self.data = data
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class LspProcessKey:
    """Identity for one language-server process instance."""

    language_id: str
    workspace_root: str
    toolchain: str = ""

    def __post_init__(self) -> None:
        """Normalize workspace_root to absolute form."""
        if not self.language_id.strip():
            raise ValueError("language_id must be non-empty")
        root = os.path.abspath(os.path.expanduser(self.workspace_root))
        object.__setattr__(self, "workspace_root", root)


class LspProcess:
    """Stdio JSON-RPC client for one language server process."""

    def __init__(
        self,
        key: LspProcessKey,
        command: Sequence[str],
        *,
        allowlist: Iterable[str],
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
        position_encoding: LspPositionEncoding = LspPositionEncoding.UTF16,
        max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
        stderr_ring_bytes: int = 64 * 1024,
        request_timeout: float = 30.0,
        max_restarts: int = 3,
        backoff_initial: float = 0.05,
        backoff_max: float = 2.0,
        popen: PopenFactory = subprocess.Popen,
    ) -> None:
        if not command:
            raise ValueError("command must be non-empty")
        self.key = key
        self._command = tuple(str(c) for c in command)
        self._allowlist = tuple(str(a) for a in allowlist)
        self._env = dict(env) if env is not None else None
        self._cwd = cwd if cwd is not None else key.workspace_root
        self.codec = LspPositionCodec(position_encoding)
        self._max_message_bytes = max_message_bytes
        self._stderr_ring_bytes = max(1024, stderr_ring_bytes)
        self._request_timeout = request_timeout
        self._max_restarts = max(0, max_restarts)
        self._backoff_initial = backoff_initial
        self._backoff_max = backoff_max
        self._popen = popen

        self._state = LspProcessState.IDLE
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._write_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._pending: MutableMapping[int | str, Future] = {}
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._stderr_chunks: deque[bytes] = deque()
        self._stderr_size = 0
        self._stderr_thread: threading.Thread | None = None
        self._restart_count = 0
        self._closing = False
        self._initialized = False
        self._notifications: deque[dict[str, Any]] = deque(maxlen=256)

    @property
    def state(self) -> LspProcessState:
        """Current lifecycle state."""
        return self._state

    @property
    def initialized(self) -> bool:
        """True after a successful ``initialize`` / ``initialized`` handshake."""
        return self._initialized

    def stderr_text(self) -> str:
        """Return the bounded stderr ring as UTF-8 (lossy)."""
        return b"".join(self._stderr_chunks).decode("utf-8", errors="replace")

    def drain_notifications(self) -> list[dict[str, Any]]:
        """Pop queued server notifications (method + params)."""
        items: list[dict[str, Any]] = []
        while self._notifications:
            items.append(self._notifications.popleft())
        return items

    def ensure_started(self) -> None:
        """Lazy-start the subprocess (spawn-gated); no-op when already running."""
        with self._lifecycle_lock:
            if self._closing or self._state in (
                LspProcessState.STOPPING,
                LspProcessState.STOPPED,
            ):
                raise LspProtocolError("LspProcess is closing")
            if self._state is LspProcessState.RUNNING and self._proc is not None:
                if self._proc.poll() is None:
                    return
                self._fail_pending("language server exited unexpectedly")
                self._cleanup_proc_unlocked()
                self._restart_unlocked()
                return
            self._start_unlocked()

    def start(self) -> None:
        """Explicit start (same as :meth:`ensure_started`)."""
        self.ensure_started()

    def initialize(
        self,
        *,
        root_uri: str | None = None,
        process_id: int | None = None,
        client_info: Mapping[str, str] | None = None,
        capabilities: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Run ``initialize`` then notify ``initialized``."""
        self.ensure_started()
        params: dict[str, Any] = {
            "processId": os.getpid() if process_id is None else process_id,
            "rootUri": root_uri or _path_to_uri(self.key.workspace_root),
            "capabilities": dict(capabilities or {}),
            "clientInfo": dict(client_info or {"name": "codimension", "version": "0"}),
        }
        result = self.request("initialize", params, timeout=timeout)
        self.notify("initialized", {})
        self._initialized = True
        return result if isinstance(result, dict) else {}

    def request(
        self,
        method: str,
        params: Any = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        """Send a JSON-RPC request and wait for the matching response."""
        self.ensure_started()
        request_id = self._allocate_id()
        future: Future = Future()
        self._pending[request_id] = future
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        try:
            self._write(message)
            return future.result(timeout=self._request_timeout if timeout is None else timeout)
        except TimeoutError as exc:
            self.cancel(request_id)
            pending = self._pending.pop(request_id, None)
            if pending is not None and not pending.done():
                pending.set_exception(LspProtocolError(f"LSP request timed out: {method}"))
            raise LspProtocolError(f"LSP request timed out: {method}") from exc
        finally:
            self._pending.pop(request_id, None)

    def notify(self, method: str, params: Any = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        self.ensure_started()
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._write(message)

    def cancel(self, request_id: int | str) -> None:
        """Send ``$/cancelRequest`` for ``request_id`` (best-effort)."""
        if self._state is not LspProcessState.RUNNING:
            return
        try:
            self._write({"jsonrpc": "2.0", "method": "$/cancelRequest", "params": {"id": request_id}})
        except (LspProtocolError, OSError, LspFramingError):
            return

    def shutdown(self, *, timeout: float = 5.0) -> None:
        """LSP ``shutdown`` → ``exit``, then force-terminate if needed."""
        with self._lifecycle_lock:
            if self._state in (LspProcessState.STOPPED, LspProcessState.STOPPING):
                return
            self._state = LspProcessState.STOPPING
        try:
            if self._proc is not None and self._proc.poll() is None:
                if self._initialized:
                    try:
                        self._request_while_running("shutdown", None, timeout=timeout)
                    except (LspProtocolError, TimeoutError, OSError):
                        pass
                try:
                    self._write({"jsonrpc": "2.0", "method": "exit"})
                except (LspProtocolError, OSError, LspFramingError, BrokenPipeError):
                    pass
        finally:
            with self._lifecycle_lock:
                self._closing = True
                self._terminate_unlocked(timeout=timeout)
                self._state = LspProcessState.STOPPED
                self._initialized = False
                self._fail_pending("LspProcess shut down")

    # --- internals ---------------------------------------------------------

    def _allocate_id(self) -> int:
        with self._id_lock:
            rid = self._next_id
            self._next_id += 1
            return rid

    def _request_while_running(
        self,
        method: str,
        params: Any,
        *,
        timeout: float,
    ) -> Any:
        """Send a request without lazy-start / restart (used during shutdown)."""
        request_id = self._allocate_id()
        future: Future = Future()
        self._pending[request_id] = future
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        try:
            self._write(message)
            return future.result(timeout=timeout)
        except TimeoutError as exc:
            self.cancel(request_id)
            raise LspProtocolError(f"LSP request timed out: {method}") from exc
        finally:
            self._pending.pop(request_id, None)

    def _start_unlocked(self) -> None:
        self._state = LspProcessState.STARTING
        binary = require_language_server_spawn(self._command[0], self._allowlist)
        argv = (binary, *self._command[1:])
        try:
            proc = self._popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self._cwd,
                env=self._env,
                bufsize=0,
            )
        except LanguageServerSpawnError:
            self._state = LspProcessState.FAILED
            raise
        except OSError as exc:
            self._state = LspProcessState.FAILED
            raise LspProtocolError(f"failed to spawn language server: {exc}") from exc
        self._proc = proc
        self._reader = threading.Thread(
            target=self._reader_loop,
            name=f"lsp-reader-{self.key.language_id}",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._stderr_loop,
            name=f"lsp-stderr-{self.key.language_id}",
            daemon=True,
        )
        self._reader.start()
        self._stderr_thread.start()
        self._state = LspProcessState.RUNNING

    def _restart_unlocked(self) -> None:
        if self._closing:
            raise LspProtocolError("LspProcess is closing")
        if self._restart_count >= self._max_restarts:
            self._state = LspProcessState.FAILED
            raise LspProtocolError(f"language server restart budget exhausted ({self._max_restarts})")
        delay = min(
            self._backoff_max,
            self._backoff_initial * (2**self._restart_count),
        )
        self._restart_count += 1
        time.sleep(delay)
        self._initialized = False
        self._start_unlocked()

    def _cleanup_proc_unlocked(self) -> None:
        self._proc = None
        self._reader = None
        self._stderr_thread = None

    def _terminate_unlocked(self, *, timeout: float) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
        finally:
            self._cleanup_proc_unlocked()

    def _write(self, message: Mapping[str, Any]) -> None:
        frame = encode_message(message)
        body = frame.split(b"\r\n\r\n", 1)[1]
        if len(body) > self._max_message_bytes:
            raise LspFramingError(
                f"outbound LSP message {len(body)} exceeds max_message_bytes={self._max_message_bytes}"
            )
        with self._write_lock:
            proc = self._proc
            if proc is None or proc.stdin is None or proc.poll() is not None:
                raise LspProtocolError("language server is not running")
            try:
                proc.stdin.write(frame)
                proc.stdin.flush()
            except BrokenPipeError as exc:
                raise LspProtocolError("language server stdin closed") from exc

    def _reader_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            while not self._closing:
                try:
                    message = read_message(proc.stdout, max_message_bytes=self._max_message_bytes)
                except EOFError:
                    break
                except LspFramingError as exc:
                    self._fail_pending(str(exc))
                    break
                self._dispatch(message)
        finally:
            if not self._closing:
                self._fail_pending("language server stdout closed")

    def _stderr_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            while True:
                chunk = proc.stderr.read(4096)
                if not chunk:
                    break
                self._stderr_chunks.append(chunk)
                self._stderr_size += len(chunk)
                while self._stderr_size > self._stderr_ring_bytes and self._stderr_chunks:
                    dropped = self._stderr_chunks.popleft()
                    self._stderr_size -= len(dropped)
        except OSError:
            return

    def _dispatch(self, message: Mapping[str, Any]) -> None:
        if "id" in message and ("result" in message or "error" in message):
            request_id = message["id"]
            future = self._pending.get(request_id)
            if future is None or future.done():
                return
            if "error" in message:
                err = message["error"] or {}
                future.set_exception(
                    LspProtocolError(
                        str(err.get("message", "LSP error")),
                        code=err.get("code"),
                        data=err.get("data"),
                    )
                )
            else:
                future.set_result(message.get("result"))
            return
        if "method" in message:
            self._notifications.append(dict(message))

    def _fail_pending(self, reason: str) -> None:
        pending = list(self._pending.items())
        self._pending.clear()
        for _, future in pending:
            if not future.done():
                future.set_exception(LspProtocolError(reason))


class LspProcessRegistry:
    """Map of :class:`LspProcessKey` → :class:`LspProcess` (lazy create)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: dict[LspProcessKey, LspProcess] = {}

    def get(self, key: LspProcessKey) -> LspProcess | None:
        """Return an existing process or ``None``."""
        with self._lock:
            return self._processes.get(key)

    def get_or_create(
        self,
        key: LspProcessKey,
        command: Sequence[str],
        *,
        allowlist: Iterable[str],
        **kwargs: Any,
    ) -> LspProcess:
        """Return existing process for ``key`` or create (not yet started)."""
        with self._lock:
            existing = self._processes.get(key)
            if existing is not None:
                return existing
            proc = LspProcess(key, command, allowlist=allowlist, **kwargs)
            self._processes[key] = proc
            return proc

    def keys(self) -> tuple[LspProcessKey, ...]:
        """Registered process keys."""
        with self._lock:
            return tuple(self._processes)

    def shutdown_all(self) -> None:
        """Shut down every process (workspace unload)."""
        with self._lock:
            procs = list(self._processes.values())
            self._processes.clear()
        for proc in procs:
            proc.shutdown()

    def shutdown_workspace(self, workspace_root: str) -> None:
        """Shut down processes whose key matches ``workspace_root``."""
        root = os.path.abspath(os.path.expanduser(workspace_root))
        with self._lock:
            victims = [k for k in self._processes if k.workspace_root == root]
            procs = [self._processes.pop(k) for k in victims]
        for proc in procs:
            proc.shutdown()


def _path_to_uri(path: str) -> str:
    """Minimal ``file://`` URI for local absolute paths."""
    abs_path = os.path.abspath(path)
    return "file://" + abs_path


__all__ = [
    "LspProcess",
    "LspProcessKey",
    "LspProcessRegistry",
    "LspProcessState",
    "LspProtocolError",
]
