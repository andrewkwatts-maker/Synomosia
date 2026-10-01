"""Rust backend loader for synomosia.

The implementation lives in the `augur_core` crate; this package is a wrapper
over it. Loading it is therefore a fact worth knowing, not an optimisation to
be applied when convenient, and this module exists to make that fact visible.

What it does *not* do is fall back. The previous `__init__.py` shipped a
pure-Python copy of every accelerated function under
``except ImportError: _RUST_CORE = False``, so a wheel built without the
extension imported cleanly, ran the Python copy, and reported nothing. Worse,
the two copies had already drifted -- the Rust keyword extractor measured its
minimum word length in bytes and ordered ties by hash, the Python one measured
characters and ordered ties stably -- so which one you got changed the answers.

Here, a missing extension leaves the package importable (so
:func:`backend_report` can explain itself) but replaces every accelerated
symbol with one that raises :class:`RustBackendUnavailable` when called.

Call :func:`assert_rust_backend` at startup to fail immediately instead.
"""
from __future__ import annotations

import warnings

# Canonical package version. `synomosia.__version__` re-exports it, and
# `augur_core`'s Cargo.toml carries the same string; `assert_rust_backend`
# compares the two. Bump all three together with the git tag.
PACKAGE_VERSION = "1.2.0"

#: Accelerated callables the extension provides. Used both for the real import
#: and to synthesise the raising stubs, so the two paths cannot drift apart.
_FUNCTIONS = (
    "article_id",
    "extract_keywords",
    "first_occurrences",
    "is_rust_backend",
    "rank_articles",
    "score_article",
    "strip_html",
    "top_categories",
    "version_rust",
)

#: Plain values the extension exports. They need a separate list because the
#: degraded path substitutes a raising *callable* for everything else, and a
#: constant is not called.
_CONSTANTS = (
    "ID_HEX_CHARS",
    "MAX_SEQUENCE_LEN",
    "MAX_TEXT_BYTES",
    "MIN_KEYWORD_CHARS",
    "SCORE_CONTENT_CONTAINS",
    "SCORE_TITLE_CONTAINS",
    "SCORE_TITLE_PREFIX",
)

_HAS_RUST = False
_REASON = ""

#: Version the loaded extension reports, recorded once at import so the
#: handshake reads the same answer every time it is asked.
_RUST_VERSION: str | None = None


class RustBackendUnavailable(RuntimeError):
    """Raised when the Rust backend is required but is not usable."""


try:
    from . import _core  # type: ignore[attr-defined]

    for _name in _FUNCTIONS + _CONSTANTS:
        globals()[_name] = getattr(_core, _name)
    del _name
    _HAS_RUST = True
    _RUST_VERSION = str(_core.version_rust())
    if _RUST_VERSION != PACKAGE_VERSION:
        _REASON = (
            f"synomosia._core reports version {_RUST_VERSION!r} but the package "
            f"is {PACKAGE_VERSION!r}. That is a stale extension left over from "
            "an earlier build; rebuild with "
            "`python -m maturin develop --features extension-module`."
        )
        # Loud rather than fatal: the import must still succeed so
        # `backend_report()` can explain itself, but nothing about a stale
        # build is allowed to be quiet.
        warnings.warn(_REASON, RuntimeWarning, stacklevel=2)
except ImportError as _import_error:  # pragma: no cover - depends on build
    _REASON = (
        "synomosia._core failed to load ({}). Install the prebuilt wheel or "
        "run `python -m maturin develop --features extension-module`."
    ).format(_import_error)

    def _missing(symbol: str):
        """Build a stand-in that raises rather than degrading silently."""

        def _raise(*_args, **_kwargs):
            raise RustBackendUnavailable(f"synomosia.{symbol} unavailable: {_REASON}")

        return _raise

    def is_rust_backend() -> bool:  # type: ignore[misc]
        return False

    def version_rust() -> str:  # type: ignore[misc]
        return ""

    for _name in _FUNCTIONS:
        if _name not in ("is_rust_backend", "version_rust"):
            globals()[_name] = _missing(_name)

    for _name in _CONSTANTS:
        globals()[_name] = None
    del _name


def assert_rust_backend() -> None:
    """Raise :class:`RustBackendUnavailable` unless the backend is live.

    ``_HAS_RUST`` alone only says the extension imported. This additionally
    checks the version handshake, because a stale ``_core`` left in the source
    tree from an earlier build is easy to miss and produces behaviour that
    matches no version of the source.
    """
    if not _HAS_RUST:
        raise RustBackendUnavailable(
            _REASON
            or "synomosia._core is not available; build it with "
            "`python -m maturin develop --features extension-module`."
        )
    if str(_RUST_VERSION) != PACKAGE_VERSION:
        raise RustBackendUnavailable(
            _REASON
            or f"extension version {_RUST_VERSION!r} does not match the Python "
            f"package version {PACKAGE_VERSION!r}; rebuild with "
            "`python -m maturin develop --features extension-module`."
        )


def backend_report() -> dict:
    """Describe the backend, for diagnostics and bug reports."""
    return {
        "has_rust": _HAS_RUST,
        "rust_version": _RUST_VERSION,
        "python_version": PACKAGE_VERSION,
        "version_mismatch": (
            None
            if _HAS_RUST and str(_RUST_VERSION) == PACKAGE_VERSION
            else f"{_RUST_VERSION!r} != {PACKAGE_VERSION!r}"
        ),
        "reason": _REASON or None,
        "functions": len(_FUNCTIONS),
        "constants": len(_CONSTANTS),
    }


__all__ = [
    "PACKAGE_VERSION",
    "RustBackendUnavailable",
    "assert_rust_backend",
    "backend_report",
    "_HAS_RUST",
    *_FUNCTIONS,
    *_CONSTANTS,
]
