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

"""LspProcess: one language-server subprocess per process key (R202–R234 / R244 / R252).

Key: ``(language_id, workspace_root, toolchain)``. Spawn is gated by
:func:`core.language_policy.require_language_server_spawn` (absolute binary on
allowlist only). Transport: JSON-RPC over stdio with Content-Length framing,
reader thread, serialized writer, cancel, timeouts, bounded stderr ring,
bounded message size, lazy start, bounded backoff restart, and
initialize → shutdown → exit on unload.

R210: server→client requests (``workspace/configuration``, progress create,
dynamic registration, ``workspace/applyEdit`` refuse+preview) are answered on
the reader thread so the language server does not hang waiting for a response.

R233: :meth:`ensure_initialized` atomically restarts a dead subprocess, runs
the LSP handshake, and bumps a process generation so callers can drop stale
document sync state. ``request`` / ``notify`` never proceed before handshake.

R234: pending Futures are keyed by ``(transport_generation, request_id)`` under
``_pending_lock``; ownership is transferred via atomic ``pop`` so timeout /
shutdown / reader races cannot raise ``InvalidStateError`` or let an old
reader fail requests belonging to a newer subprocess.

R244: outbound requests bind pending registration + stdin write under one
transport lease ``(proc, transport_generation)`` so a restart cannot register
against gen N and write to gen N+1. Server→client replies write to the
*reader's* ``proc``; stale-generation notifications and capability side
effects never mutate the live process state.

R252: application ``request`` / ``notify`` obtain an *initialized* transport
lease — ``ensure_alive`` + handshake + pending bind/write run under
:attr:`_lifecycle_lock` so a restart cannot accept app RPC on a transport
whose handshake is still in flight.

R253: ``request(..., expect_generation=N)`` refuses to write when handshake
generation is no longer ``N``, so semantic callers can resync ``didOpen``
before retrying instead of querying a virgin process.

R262: ``notify(..., expect_generation=N)`` shares the same pin so a restart
inside document sync cannot silently deliver ``didChange`` to a virgin
generation without a preceding ``didOpen``.

R266: reader and stderr workers bind an immutable ``(proc, transport_generation)``
lease; reader EOF / framing failure invalidates that transport so the next
``ensure_alive`` restarts instead of writing to a live process with a dead
stdout reader.

R256: ``_bind_pending_and_write`` rolls back the pending Future if encode/write
fails so timeout/shutdown cannot settle a leaked registration.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections import deque
from concurrent.futures import Future, InvalidStateError
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from core.language_policy import LanguageServerSpawnError, require_language_server_spawn
from infrastructure.lsp_framing import (
    DEFAULT_MAX_MESSAGE_BYTES,
    LspFramingError,
    encode_message,
    read_message,
)
from infrastructure.lsp_position_codec import LspPositionCodec, LspPositionEncoding

PopenFactory = Callable[..., subprocess.Popen]

# JSON-RPC / LSP error codes used when refusing unknown server requests.
_JSONRPC_METHOD_NOT_FOUND = -32601
_APPLY_EDIT_REFUSE_REASON = "Codimension does not auto-apply workspace/applyEdit; preview only (R210)"


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


@dataclass(frozen=True, slots=True)
class _TransportLease:
    """Snapshot of the live subprocess + transport / handshake generations.

    R244: ``proc`` + ``generation`` (transport) for pending+write atomicity.
    R252: ``initialized_generation`` is the handshake generation when the lease
    was taken after a completed ``initialize``/``initialized``; ``0`` means
    the lease is not app-ready (handshake-only I/O).
    """

    proc: subprocess.Popen
    generation: int
    initialized_generation: int = 0


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
        # R234: (transport_generation, request_id) → Future
        self._pending: dict[tuple[int, int | str], Future] = {}
        self._pending_lock = threading.Lock()
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._stderr_chunks: deque[bytes] = deque()
        self._stderr_size = 0
        self._stderr_thread: threading.Thread | None = None
        self._restart_count = 0
        self._closing = False
        self._initialized = False
        # Bumped after each successful initialize handshake (R233).
        self._generation = 0
        # Bumped on every subprocess spawn; keys pending futures (R234).
        self._transport_generation = 0
        # R266: set to the live transport generation when its reader dies while
        # the subprocess may still be alive (closed stdout / framing failure).
        self._broken_transport_generation = 0
        self._last_initialize_result: dict[str, Any] = {}
        self._notifications: deque[dict[str, Any]] = deque(maxlen=256)
        self._apply_edit_previews: deque[dict[str, Any]] = deque(maxlen=64)
        self._dynamic_registrations: dict[str, Mapping[str, Any]] = {}
        self._registrations_lock = threading.Lock()

    @property
    def state(self) -> LspProcessState:
        """Current lifecycle state."""
        return self._state

    @property
    def initialized(self) -> bool:
        """True after a successful ``initialize`` / ``initialized`` handshake."""
        return self._initialized

    @property
    def generation(self) -> int:
        """Monotonic process generation; increments on each successful handshake."""
        return self._generation

    def stderr_text(self) -> str:
        """Return the bounded stderr ring as UTF-8 (lossy)."""
        return b"".join(self._stderr_chunks).decode("utf-8", errors="replace")

    def drain_notifications(self) -> list[dict[str, Any]]:
        """Pop queued server notifications (method + params)."""
        items: list[dict[str, Any]] = []
        while self._notifications:
            items.append(self._notifications.popleft())
        return items

    def drain_apply_edit_previews(self) -> list[dict[str, Any]]:
        """Pop refused ``workspace/applyEdit`` payloads queued for UI preview."""
        items: list[dict[str, Any]] = []
        while self._apply_edit_previews:
            items.append(self._apply_edit_previews.popleft())
        return items

    def dynamic_registrations(self) -> tuple[Mapping[str, Any], ...]:
        """Return a snapshot of accepted ``client/registerCapability`` entries."""
        with self._registrations_lock:
            return tuple(dict(v) for v in self._dynamic_registrations.values())

    def ensure_started(self) -> None:
        """Lazy-start the subprocess (spawn-gated); no-op when already running."""
        with self._lifecycle_lock:
            self._ensure_alive_unlocked()

    def ensure_initialized(
        self,
        *,
        root_uri: str | None = None,
        process_id: int | None = None,
        client_info: Mapping[str, str] | None = None,
        capabilities: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> int:
        """Ensure a live subprocess and completed LSP handshake (R233).

        Under the lifecycle lock this method:

        1. checks the subprocess (restarting if it exited);
        2. runs ``initialize`` / ``initialized`` when needed;
        3. bumps :attr:`generation` after a successful handshake;
        4. returns the current generation for callers to invalidate sync state.

        Handshake I/O uses :meth:`_request_while_running` / :meth:`_write` so it
        does not re-enter :meth:`ensure_started` while the lock is held.
        Outbound RPC binds pending + write on one transport lease (R244).
        """
        with self._lifecycle_lock:
            self._ensure_alive_unlocked()
            if not self._initialized:
                self._handshake_unlocked(
                    root_uri=root_uri,
                    process_id=process_id,
                    client_info=client_info,
                    capabilities=capabilities,
                    timeout=timeout,
                )
            return self._generation

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
        """Run ``initialize`` then notify ``initialized``.

        Advertises default client capabilities (R210) merged with any caller
        overrides, then negotiates ``positionEncoding`` from the server result.
        Equivalent to :meth:`ensure_initialized` with a forced handshake when
        already initialized (explicit re-init for tests / recovery).
        """
        with self._lifecycle_lock:
            self._ensure_alive_unlocked()
            return self._handshake_unlocked(
                root_uri=root_uri,
                process_id=process_id,
                client_info=client_info,
                capabilities=capabilities,
                timeout=timeout,
            )

    def request(
        self,
        method: str,
        params: Any = None,
        *,
        timeout: float | None = None,
        expect_generation: int | None = None,
    ) -> Any:
        """Send a JSON-RPC request and wait for the matching response.

        R252: for application methods, alive-check + handshake + pending bind
        and stdin write occur under :attr:`_lifecycle_lock` so a concurrent
        restart cannot register/write against an uninitialized transport.

        R253: when ``expect_generation`` is set, refuse to write if the live
        handshake generation differs (caller must resync documents first).
        """
        request_id = self._allocate_id()
        future: Future = Future()
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        if method == "initialize":
            # Handshake path uses :meth:`_handshake_unlocked`; public initialize
            # RPC still requires a live process but not a prior handshake.
            self.ensure_started()
            pending_key = self._bind_pending_and_write(request_id, future, message, require_initialized=False)
        else:
            with self._lifecycle_lock:
                self._ensure_alive_unlocked()
                if not self._initialized:
                    self._handshake_unlocked()
                if expect_generation is not None and self._generation != expect_generation:
                    raise LspProtocolError("language server generation changed; resync documents before retry")
                pending_key = self._bind_pending_and_write(request_id, future, message, require_initialized=True)
        try:
            return future.result(timeout=self._request_timeout if timeout is None else timeout)
        except Exception as exc:
            if not (isinstance(exc, TimeoutError) or type(exc).__name__ == "TimeoutError"):
                raise
            self.cancel(request_id)
            pending = self._pop_pending(pending_key)
            self._settle_future(
                pending,
                exception=LspProtocolError(f"LSP request timed out: {method}"),
            )
            raise LspProtocolError(f"LSP request timed out: {method}") from exc
        finally:
            self._pop_pending(pending_key)

    def notify(
        self,
        method: str,
        params: Any = None,
        *,
        expect_generation: int | None = None,
    ) -> None:
        """Send a JSON-RPC notification (no response expected).

        R252: application notifications share the initialized-lease barrier
        with :meth:`request` (``initialized`` itself is handshake-only).

        R262: when ``expect_generation`` is set, refuse to write if the live
        handshake generation differs (caller must clear open tracking and
        re-``didOpen`` before retrying).
        """
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if method == "initialized":
            self.ensure_started()
            self._write(message, require_initialized=False)
            return
        with self._lifecycle_lock:
            self._ensure_alive_unlocked()
            if not self._initialized:
                self._handshake_unlocked()
            if expect_generation is not None and self._generation != expect_generation:
                raise LspProtocolError("language server generation changed; resync documents before retry")
            self._write(message, require_initialized=True)

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
                    except Exception as exc:  # noqa: BLE001 — futures TimeoutError alias drift
                        if type(exc).__name__ != "TimeoutError":
                            raise
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

    def _ensure_alive_unlocked(self) -> None:
        """Start or restart the subprocess; does not run the LSP handshake."""
        if self._closing or self._state in (
            LspProcessState.STOPPING,
            LspProcessState.STOPPED,
        ):
            raise LspProtocolError("LspProcess is closing")
        if self._state is LspProcessState.RUNNING and self._proc is not None:
            broken = self._broken_transport_generation == self._transport_generation
            alive = self._proc.poll() is None
            if alive and not broken:
                return
            reason = (
                "language server transport broken (reader died)" if broken else "language server exited unexpectedly"
            )
            self._fail_pending(reason, generation=self._transport_generation)
            proc = self._proc
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=2.0)
                except (subprocess.TimeoutExpired, OSError):
                    pass
            self._cleanup_proc_unlocked()
            self._broken_transport_generation = 0
            self._restart_unlocked()
            return
        self._start_unlocked()

    def _handshake_unlocked(
        self,
        *,
        root_uri: str | None = None,
        process_id: int | None = None,
        client_info: Mapping[str, str] | None = None,
        capabilities: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Run initialize handshake while holding :attr:`_lifecycle_lock` (R233)."""
        client_caps = _merge_client_capabilities(default_client_capabilities(), capabilities)
        params: dict[str, Any] = {
            "processId": os.getpid() if process_id is None else process_id,
            "rootUri": root_uri or _path_to_uri(self.key.workspace_root),
            "capabilities": client_caps,
            "clientInfo": dict(client_info or {"name": "codimension", "version": "0"}),
        }
        wait = self._request_timeout if timeout is None else timeout
        result = self._request_while_running("initialize", params, timeout=wait)
        if isinstance(result, dict):
            self._apply_negotiated_position_encoding(result)
            self._last_initialize_result = dict(result)
        else:
            self._last_initialize_result = {}
        # Notification must not call ensure_initialized (would re-enter lock).
        self._write({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        self._initialized = True
        self._generation += 1
        return self._last_initialize_result

    def _allocate_id(self) -> int:
        with self._id_lock:
            rid = self._next_id
            self._next_id += 1
            return rid

    def _put_pending(self, request_id: int | str, future: Future) -> tuple[int, int | str]:
        """Register ``future`` under the current transport generation (R234).

        Prefer :meth:`_bind_pending_and_write` for live RPC so generation and
        stdin target cannot diverge (R244).
        """
        with self._pending_lock:
            key = (self._transport_generation, request_id)
            self._pending[key] = future
            return key

    def _pop_pending(self, key: tuple[int, int | str]) -> Future | None:
        """Atomically take ownership of a pending future (or ``None``)."""
        with self._pending_lock:
            return self._pending.pop(key, None)

    @staticmethod
    def _settle_future(
        future: Future | None,
        *,
        result: Any = None,
        exception: BaseException | None = None,
    ) -> None:
        """Complete ``future`` once; ignore late races (R234)."""
        if future is None or future.done():
            return
        try:
            if exception is not None:
                future.set_exception(exception)
            else:
                future.set_result(result)
        except InvalidStateError:
            return

    def _require_running_proc_unlocked(self) -> subprocess.Popen:
        """Return the live subprocess; caller must hold :attr:`_write_lock`."""
        proc = self._proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            raise LspProtocolError("language server is not running")
        return proc

    def _lease_unlocked(self, *, require_initialized: bool = False) -> _TransportLease:
        """Capture ``(proc, transport_generation[, initialized_generation])`` (R244 / R252).

        Caller must hold :attr:`_write_lock`. When ``require_initialized`` is
        true, refuse leases for transports that have not finished handshake.
        """
        proc = self._require_running_proc_unlocked()
        if require_initialized and not self._initialized:
            raise LspProtocolError("language server is not initialized")
        return _TransportLease(
            proc=proc,
            generation=self._transport_generation,
            initialized_generation=self._generation if self._initialized else 0,
        )

    def _encode_and_write_unlocked(self, proc: subprocess.Popen, message: Mapping[str, Any]) -> None:
        """Write a framed message to ``proc.stdin``; caller holds :attr:`_write_lock`."""
        frame = encode_message(message)
        body = frame.split(b"\r\n\r\n", 1)[1]
        if len(body) > self._max_message_bytes:
            raise LspFramingError(
                f"outbound LSP message {len(body)} exceeds max_message_bytes={self._max_message_bytes}"
            )
        if proc.stdin is None or proc.poll() is not None:
            raise LspProtocolError("language server is not running")
        try:
            proc.stdin.write(frame)
            proc.stdin.flush()
        except BrokenPipeError as exc:
            raise LspProtocolError("language server stdin closed") from exc

    def _bind_pending_and_write(
        self,
        request_id: int | str,
        future: Future,
        message: Mapping[str, Any],
        *,
        require_initialized: bool = False,
    ) -> tuple[int, int | str]:
        """Register pending under the lease generation and write to that proc (R244 / R252 / R256)."""
        with self._write_lock:
            lease = self._lease_unlocked(require_initialized=require_initialized)
            with self._pending_lock:
                key = (lease.generation, request_id)
                self._pending[key] = future
            try:
                self._encode_and_write_unlocked(lease.proc, message)
            except Exception:
                # R256: drop pending if write fails so futures do not leak.
                with self._pending_lock:
                    self._pending.pop(key, None)
                raise
            return key

    def _write_to_proc(self, proc: subprocess.Popen, message: Mapping[str, Any]) -> None:
        """Serialize a write to a specific subprocess (reader replies / lease)."""
        with self._write_lock:
            self._encode_and_write_unlocked(proc, message)

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
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        pending_key = self._bind_pending_and_write(request_id, future, message)
        try:
            return future.result(timeout=timeout)
        except Exception as exc:
            # Py3.10+ usually aliases futures TimeoutError to builtins; still
            # accept either so shutdown races never leak an uncaught timeout.
            if not (isinstance(exc, TimeoutError) or type(exc).__name__ == "TimeoutError"):
                raise
            self.cancel(request_id)
            pending = self._pop_pending(pending_key)
            self._settle_future(
                pending,
                exception=LspProtocolError(f"LSP request timed out: {method}"),
            )
            raise LspProtocolError(f"LSP request timed out: {method}") from exc
        finally:
            self._pop_pending(pending_key)

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
        self._transport_generation += 1
        self._broken_transport_generation = 0
        reader_generation = self._transport_generation
        # Stale capability tables belong to the previous subprocess (R244).
        with self._registrations_lock:
            self._dynamic_registrations.clear()
        self._reader = threading.Thread(
            target=self._reader_loop,
            args=(proc, reader_generation),
            name=f"lsp-reader-{self.key.language_id}",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._stderr_loop,
            args=(proc, reader_generation),
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
            try:
                proc.kill()
            except OSError:
                pass
            try:
                proc.wait(timeout=2.0)
            except (subprocess.TimeoutExpired, OSError):
                pass
        finally:
            self._cleanup_proc_unlocked()

    def _write(self, message: Mapping[str, Any], *, require_initialized: bool = False) -> None:
        """Write ``message`` to the *current* subprocess under a transport lease (R244 / R252)."""
        with self._write_lock:
            lease = self._lease_unlocked(require_initialized=require_initialized)
            self._encode_and_write_unlocked(lease.proc, message)

    def _invalidate_transport(self, proc: subprocess.Popen, generation: int, reason: str) -> None:
        """Fail pending for ``generation`` and mark that transport broken (R266).

        A live subprocess with a dead stdout reader must not accept further app
        RPC until :meth:`_ensure_alive_unlocked` restarts it.
        """
        with self._lifecycle_lock:
            self._fail_pending(reason, generation=generation)
            if self._closing:
                return
            if generation != self._transport_generation or self._proc is not proc:
                return
            # Do not clear ``_initialized`` here: a crashed subprocess can leave
            # that flag True until ``_ensure_alive_unlocked`` restarts (R233).
            # The broken-generation marker alone forces restart even when poll()
            # still reports alive (reader died first).
            self._broken_transport_generation = generation
            try:
                if proc.poll() is None:
                    proc.kill()
            except OSError:
                return

    def _reader_loop(self, proc: subprocess.Popen, generation: int) -> None:
        """Read stdout for one subprocess generation (R234 / R244 / R266)."""
        if proc.stdout is None:
            return
        try:
            while not self._closing:
                try:
                    message = read_message(proc.stdout, max_message_bytes=self._max_message_bytes)
                except EOFError:
                    break
                except LspFramingError as exc:
                    self._invalidate_transport(proc, generation, str(exc))
                    return
                try:
                    self._dispatch(message, generation, proc)
                except Exception:  # noqa: BLE001 — keep reader alive across settle races
                    continue
        finally:
            # Only settle / invalidate *this* subprocess; a newer restart keeps its pending.
            if not self._closing:
                self._invalidate_transport(proc, generation, "language server stdout closed")

    def _stderr_loop(self, proc: subprocess.Popen, generation: int) -> None:
        """Drain stderr for one subprocess lease (R266); ignore superseded procs."""
        del generation  # lease identity; stderr is best-effort for this proc only
        if proc.stderr is None:
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

    def _dispatch(
        self,
        message: Mapping[str, Any],
        generation: int,
        proc: subprocess.Popen,
    ) -> None:
        """Handle one inbound frame scoped to the reader's transport lease (R244)."""
        if "id" in message and ("result" in message or "error" in message):
            request_id = message["id"]
            # Atomic pop transfers ownership — timeout/shutdown cannot double-settle.
            future = self._pop_pending((generation, request_id))
            if future is None:
                return
            if "error" in message:
                err = message["error"] or {}
                self._settle_future(
                    future,
                    exception=LspProtocolError(
                        str(err.get("message", "LSP error")),
                        code=err.get("code"),
                        data=err.get("data"),
                    ),
                )
            else:
                self._settle_future(future, result=message.get("result"))
            return
        if "method" in message and "id" in message:
            # Server → client request: reply on *this* reader's pipe (R244).
            self._handle_server_request(message, generation=generation, reply_proc=proc)
            return
        if "method" in message:
            # Drop notifications from a superseded transport generation (R244).
            if generation != self._transport_generation:
                return
            self._notifications.append(dict(message))

    def _handle_server_request(
        self,
        message: Mapping[str, Any],
        *,
        generation: int,
        reply_proc: subprocess.Popen,
    ) -> None:
        """Answer a JSON-RPC request originating from the language server."""
        request_id = message["id"]
        method = str(message.get("method") or "")
        params = message.get("params")
        # Side effects only when this reader still owns the live transport (R244).
        apply_side_effects = generation == self._transport_generation
        try:
            result = self._server_request_result(
                method,
                params,
                apply_side_effects=apply_side_effects,
            )
        except Exception as exc:  # noqa: BLE001 — map to JSON-RPC error response
            self._reply_error(
                request_id,
                code=-32603,
                message=f"internal error handling {method}: {exc}",
                reply_proc=reply_proc,
            )
            return
        if result is _METHOD_NOT_FOUND:
            self._reply_error(
                request_id,
                code=_JSONRPC_METHOD_NOT_FOUND,
                message=f"Method not found: {method}",
                reply_proc=reply_proc,
            )
            return
        self._reply_result(request_id, result, reply_proc=reply_proc)

    def _server_request_result(
        self,
        method: str,
        params: Any,
        *,
        apply_side_effects: bool = True,
    ) -> Any:
        """Compute the JSON-RPC ``result`` for a known server→client method."""
        if method == "workspace/configuration":
            items = ()
            if isinstance(params, Mapping):
                raw = params.get("items")
                if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
                    items = tuple(raw)
            # No IDE settings bridge yet — null per item keeps servers alive.
            return [None] * len(items)

        if method == "window/workDoneProgress/create":
            return None

        if method == "client/registerCapability":
            registrations: list[Mapping[str, Any]] = []
            if isinstance(params, Mapping):
                raw = params.get("registrations")
                if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
                    registrations = [r for r in raw if isinstance(r, Mapping)]
            if apply_side_effects:
                with self._registrations_lock:
                    for reg in registrations:
                        reg_id = str(reg.get("id", ""))
                        if reg_id:
                            self._dynamic_registrations[reg_id] = dict(reg)
            return None

        if method == "client/unregisterCapability":
            unregister: list[Mapping[str, Any]] = []
            if isinstance(params, Mapping):
                raw = params.get("unregisterations") or params.get("unregistrations")
                if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
                    unregister = [r for r in raw if isinstance(r, Mapping)]
            if apply_side_effects:
                with self._registrations_lock:
                    for reg in unregister:
                        reg_id = str(reg.get("id", ""))
                        if reg_id:
                            self._dynamic_registrations.pop(reg_id, None)
            return None

        if method == "workspace/applyEdit":
            preview: dict[str, Any] = {}
            if isinstance(params, Mapping):
                preview = dict(params)
            if apply_side_effects:
                self._apply_edit_previews.append(preview)
            return {
                "applied": False,
                "failureReason": _APPLY_EDIT_REFUSE_REASON,
            }

        if method == "window/showMessageRequest":
            # Pick no action — UI bridge is out of R210 scope.
            return None

        return _METHOD_NOT_FOUND

    def _reply_result(
        self,
        request_id: int | str,
        result: Any,
        *,
        reply_proc: subprocess.Popen | None = None,
    ) -> None:
        """Send a successful JSON-RPC response for a server request."""
        target = reply_proc if reply_proc is not None else self._proc
        if target is None:
            return
        try:
            self._write_to_proc(target, {"jsonrpc": "2.0", "id": request_id, "result": result})
        except (LspProtocolError, OSError, LspFramingError, BrokenPipeError):
            return

    def _reply_error(
        self,
        request_id: int | str,
        *,
        code: int,
        message: str,
        reply_proc: subprocess.Popen | None = None,
    ) -> None:
        """Send a JSON-RPC error response for a server request."""
        target = reply_proc if reply_proc is not None else self._proc
        if target is None:
            return
        try:
            self._write_to_proc(
                target,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": code, "message": message},
                },
            )
        except (LspProtocolError, OSError, LspFramingError, BrokenPipeError):
            return

    def _apply_negotiated_position_encoding(self, initialize_result: Mapping[str, Any]) -> None:
        """Update :attr:`codec` when the server selects a ``positionEncoding``."""
        caps = initialize_result.get("capabilities")
        if not isinstance(caps, Mapping):
            return
        raw = caps.get("positionEncoding")
        if not isinstance(raw, str) or not raw:
            return
        try:
            encoding = LspPositionEncoding(raw)
        except ValueError:
            return
        if encoding is self.codec.encoding:
            return
        self.codec = LspPositionCodec(encoding)

    def _fail_pending(self, reason: str, *, generation: int | None = None) -> None:
        """Fail pending futures; optionally scoped to one transport generation (R234)."""
        with self._pending_lock:
            if generation is None:
                items = list(self._pending.items())
                self._pending.clear()
            else:
                items = [(key, fut) for key, fut in self._pending.items() if key[0] == generation]
                for key, _ in items:
                    del self._pending[key]
        for _, future in items:
            self._settle_future(future, exception=LspProtocolError(reason))


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
    """Canonical ``file://`` URI for local paths (R242 / R251)."""
    from infrastructure.file_uri import path_to_file_uri

    return str(path_to_file_uri(os.path.abspath(os.path.expanduser(path))))


# Sentinel returned by ``_server_request_result`` for unknown methods.
_METHOD_NOT_FOUND = object()


def default_client_capabilities() -> dict[str, Any]:
    """Client capabilities advertised on ``initialize`` (R210).

    Declares support for answering the server→client requests we handle, and
    the position encodings :class:`LspPositionCodec` can negotiate.
    """
    return {
        "general": {
            "positionEncodings": [
                LspPositionEncoding.UTF16.value,
                LspPositionEncoding.UTF8.value,
                LspPositionEncoding.UTF32.value,
            ],
        },
        "workspace": {
            "applyEdit": True,
            "configuration": True,
            "workspaceEdit": {
                "documentChanges": True,
            },
        },
        "window": {
            "workDoneProgress": True,
            "showMessage": {
                "messageActionItem": {"additionalPropertiesSupport": False},
            },
        },
    }


def _merge_client_capabilities(
    base: Mapping[str, Any],
    overrides: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Shallow-merge top-level capability groups; nested maps are updated."""
    merged: dict[str, Any] = {k: (dict(v) if isinstance(v, Mapping) else v) for k, v in base.items()}
    if not overrides:
        return merged
    for key, value in overrides.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(dict(value))
            merged[key] = nested
        else:
            merged[key] = value
    return merged


__all__ = [
    "LspProcess",
    "LspProcessKey",
    "LspProcessRegistry",
    "LspProcessState",
    "LspProtocolError",
    "default_client_capabilities",
]
