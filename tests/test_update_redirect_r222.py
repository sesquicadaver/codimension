# -*- coding: utf-8 -*-
"""R222: updater redirect hop + final URL re-validation."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request

import parsers  # noqa: E402,F401
import pytest

_CODIM = Path(__file__).resolve().parents[1] / "codimension"


@pytest.fixture(autouse=True)
def _purge_stubs():
    import importlib

    def _under(mod: object) -> bool:
        path = getattr(mod, "__file__", None)
        if path:
            return "/codimension/" in os.path.abspath(path).replace("\\", "/")
        return False

    dirty = False
    for name in list(sys.modules):
        if name not in ("ui", "utils") and not name.startswith(("ui.", "utils.")):
            continue
        if _under(sys.modules[name]):
            continue
        del sys.modules[name]
        dirty = True
    if dirty:
        importlib.invalidate_caches()
        if str(_CODIM) not in sys.path:
            sys.path.insert(0, str(_CODIM))
    yield


def test_redirect_handler_rejects_untrusted_hop() -> None:
    from utils.update_provenance import TrustedUpdateRedirectHandler, UpdateProvenanceError

    handler = TrustedUpdateRedirectHandler(purpose="download", environ={})
    req = Request("https://github.com/sesquicadaver/codimension/releases/download/v1/a.whl")
    with pytest.raises(UpdateProvenanceError, match="not trusted"):
        handler.redirect_request(
            req,
            None,
            302,
            "Found",
            {},
            "https://evil.example/a.whl",
        )


def test_redirect_handler_rejects_http_hop() -> None:
    from utils.update_provenance import TrustedUpdateRedirectHandler, UpdateProvenanceError

    handler = TrustedUpdateRedirectHandler(purpose="download", environ={})
    req = Request("https://github.com/sesquicadaver/codimension/releases/download/v1/a.whl")
    with pytest.raises(UpdateProvenanceError, match="https"):
        handler.redirect_request(
            req,
            None,
            302,
            "Found",
            {},
            "http://objects.githubusercontent.com/a.whl",
        )


def test_redirect_handler_allows_trusted_cdn_hop() -> None:
    from utils.update_provenance import TrustedUpdateRedirectHandler

    handler = TrustedUpdateRedirectHandler(purpose="download", environ={})
    req = Request("https://github.com/sesquicadaver/codimension/releases/download/v1/a.whl")
    new = handler.redirect_request(
        req,
        None,
        302,
        "Found",
        {},
        "https://objects.githubusercontent.com/github-production-release-asset/1/a.whl",
    )
    assert new is not None
    assert "objects.githubusercontent.com" in new.full_url


def test_redirect_handler_rejects_releases_api_path_escape() -> None:
    from utils.update_provenance import TrustedUpdateRedirectHandler, UpdateProvenanceError

    handler = TrustedUpdateRedirectHandler(purpose="releases_api", environ={})
    req = Request("https://api.github.com/repos/sesquicadaver/codimension/releases")
    with pytest.raises(UpdateProvenanceError, match="Releases API path"):
        handler.redirect_request(
            req,
            None,
            302,
            "Found",
            {},
            "https://api.github.com/repos/other/repo/releases",
        )


def test_trusted_urlopen_rejects_evil_final_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from utils import update_provenance as up

    closed: list[bool] = []

    class _Resp:
        def geturl(self) -> str:
            return "https://evil.example/payload"

        def close(self) -> None:
            closed.append(True)

    class _Opener:
        def open(self, req: Request, timeout: Any = None) -> _Resp:
            del req, timeout
            return _Resp()

    monkeypatch.setattr(up, "build_opener", lambda *args, **kwargs: _Opener())
    with pytest.raises(up.UpdateProvenanceError, match="not trusted"):
        up.trusted_urlopen(
            Request("https://github.com/sesquicadaver/codimension/releases/download/v1/a.whl"),
            purpose="download",
            environ={},
        )
    assert closed == [True]


def test_trusted_urlopen_accepts_trusted_final_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from utils import update_provenance as up

    class _Resp:
        def geturl(self) -> str:
            return "https://objects.githubusercontent.com/github-production-release-asset/1/a.whl"

        def read(self, n: int = -1) -> bytes:
            del n
            return b"ok"

        def close(self) -> None:
            return None

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: object) -> bool:
            del args
            return False

    class _Opener:
        def open(self, req: Request, timeout: Any = None) -> _Resp:
            del req, timeout
            return _Resp()

    monkeypatch.setattr(up, "build_opener", lambda *args, **kwargs: _Opener())
    resp = up.trusted_urlopen(
        Request("https://github.com/sesquicadaver/codimension/releases/download/v1/a.whl"),
        purpose="download",
        environ={},
    )
    assert resp.read() == b"ok"
