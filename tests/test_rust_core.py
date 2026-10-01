"""The extension's real surface, the wrapper's list of it, the stub, and parity.

Two jobs.

**Drift.** The comparison between what `synomosia._core` exports and what
`_backend` re-exports runs in *both* directions. In the sibling `arithma`
package the compiled extension exported 87 symbols while the Python wrapper
listed 42: the missing 45 were compiled into the wheel, shipped, and
unreachable. Nothing failed -- they were simply absent. The reverse direction
matters just as much: a name the wrapper advertises but the extension lacks
raises `AttributeError` at the first call instead of at import.

**Parity.** `article_id` is the primary key of every stored article, so the
digest is pinned to `hashlib`'s output here. A divergence would silently
re-insert every article already in the database under a new id.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

import synomosia
from synomosia import _backend

ROOT = Path(__file__).resolve().parents[1]

#: Names Python puts on every module object, which are not part of the
#: extension's surface.
_MODULE_DUNDERS = frozenset(
    {
        "__all__",
        "__builtins__",
        "__doc__",
        "__file__",
        "__loader__",
        "__name__",
        "__package__",
        "__spec__",
        "__path__",
        "__test__",
    }
)

#: Dunders the extension deliberately exports. `__version__` is the handshake
#: value and is checked by name below rather than through the surface sets.
_DUNDER_EXPORTS = frozenset({"__version__"})


def _extension_surface() -> set[str]:
    """Every name `synomosia._core` actually exports.

    PyO3 fills `__all__` in from the registrations themselves, so it is the
    module's own account of what it added; `dir()` is what is really reachable
    on it. Both are computed and compared, because a name in one and not the
    other means a registration and its object disagree.
    """
    core = _backend._core
    declared = set(core.__all__) - _DUNDER_EXPORTS
    visible = {
        name
        for name in dir(core)
        if name not in _MODULE_DUNDERS and not name.startswith("_")
    }
    assert declared == visible, (
        "synomosia._core.__all__ and dir() disagree: "
        f"only in __all__ {sorted(declared - visible)}, "
        f"only reachable {sorted(visible - declared)}"
    )
    return visible


def _declared_surface() -> set[str]:
    """Every name `_backend` claims the extension exports."""
    return set(_backend._FUNCTIONS) | set(_backend._CONSTANTS)


def _version_in(path: Path) -> str:
    """First `version = "..."` in a TOML file.

    A regex rather than `tomllib`, which is 3.11+ while this package supports
    3.10. Both files put the version in their first table.
    """
    text = path.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None, f"no version found in {path}"
    return match.group(1)


def _stub_surface() -> set[str]:
    """Every name declared in `_core.pyi`, minus the dunder exports."""
    text = (ROOT / "src" / "synomosia" / "_core.pyi").read_text(encoding="utf-8")
    functions = set(re.findall(r"^def ([A-Za-z_][A-Za-z0-9_]*)\(", text, re.MULTILINE))
    constants = set(
        re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*[A-Za-z]", text, re.MULTILINE)
    )
    return (functions | constants) - _DUNDER_EXPORTS


# ---------------------------------------------------------------------------
# The backend has to be there at all
# ---------------------------------------------------------------------------

def test_the_extension_is_loaded():
    """Everything below compares against a live extension, so say so first.

    A failure rather than a skip on purpose: a skipped surface test is the
    same silence this package was rewritten to remove.
    """
    assert _backend._HAS_RUST, (
        "synomosia._core is not loaded, so the surface cannot be compared. "
        "Build it with `python -m maturin develop --features extension-module`. "
        f"Reported reason: {_backend._REASON or 'none given'}"
    )


def test_assert_rust_backend_accepts_a_live_current_extension():
    synomosia.assert_rust_backend()


def test_backend_report_describes_a_healthy_backend():
    report = synomosia.backend_report()
    assert report["has_rust"] is True
    assert report["version_mismatch"] is None
    assert report["reason"] is None
    assert report["functions"] == len(_backend._FUNCTIONS)
    assert report["constants"] == len(_backend._CONSTANTS)


# ---------------------------------------------------------------------------
# Drift, both directions
# ---------------------------------------------------------------------------

def test_no_binding_is_compiled_in_and_left_unreachable():
    """Extension -> wrapper. A symbol here that is not listed is dead weight."""
    unreachable = sorted(_extension_surface() - _declared_surface())
    assert not unreachable, (
        "synomosia._core exports symbols that _backend does not re-export, so "
        "they are compiled into the wheel and unreachable from Python: "
        f"{unreachable}. Add them to _FUNCTIONS or _CONSTANTS."
    )


def test_the_wrapper_advertises_nothing_the_extension_lacks():
    """Wrapper -> extension. A name listed here that is absent raises later."""
    missing = sorted(_declared_surface() - _extension_surface())
    assert not missing, (
        "_backend lists symbols synomosia._core does not export: "
        f"{missing}. Either the extension is stale or the list is wrong."
    )


def test_the_lists_agree_with_what_the_names_actually_are():
    """A function filed as a constant (or the reverse) breaks the missing path.

    Without the extension, `_backend` substitutes a raising *callable* for
    every function and `None` for every constant. A misfiled name only shows
    up when the extension is absent, which is the one moment nobody wants a
    second bug.
    """
    for name in _backend._FUNCTIONS:
        assert callable(getattr(_backend._core, name)), (
            f"{name} is listed as a function but is not callable"
        )
    for name in _backend._CONSTANTS:
        value = getattr(_backend._core, name)
        assert not callable(value), f"{name} is listed as a constant but is callable"
        assert isinstance(value, (int, float, str)), (
            f"{name} is {type(value).__name__}, which the missing path cannot "
            "stand in for with None"
        )


def test_the_stub_matches_the_extension_both_ways():
    stub = _stub_surface()
    extension = _extension_surface()
    assert not (extension - stub), (
        f"_core.pyi is missing {sorted(extension - stub)}; type checkers will "
        "reject calls that work at runtime."
    )
    assert not (stub - extension), (
        f"_core.pyi declares {sorted(stub - extension)}, which the extension "
        "does not export; type checkers will accept calls that raise."
    )


def test_the_package_re_exports_every_accelerated_function():
    """`import synomosia; synomosia.strip_html(...)` has to keep working."""
    exported = set(synomosia.__all__)
    for name in _backend._FUNCTIONS:
        assert name in exported, f"synomosia.__all__ omits {name}"
        assert callable(getattr(synomosia, name)), f"synomosia.{name} is not callable"


# ---------------------------------------------------------------------------
# The version handshake
# ---------------------------------------------------------------------------

def test_the_version_is_the_same_in_all_four_places():
    """pyproject, Cargo.toml, the package and the compiled extension.

    Not cosmetic: `assert_rust_backend()` refuses to run on a mismatch, and
    the point of that refusal is to catch a stale `_core` left in the tree
    from an earlier build.
    """
    pyproject = _version_in(ROOT / "pyproject.toml")
    crate = _version_in(ROOT / "rust" / "augur_core" / "Cargo.toml")
    assert pyproject == crate == _backend.PACKAGE_VERSION == synomosia.__version__, (
        f"pyproject={pyproject!r} crate={crate!r} "
        f"package={_backend.PACKAGE_VERSION!r} dunder={synomosia.__version__!r}"
    )
    assert synomosia.version_rust() == _backend.PACKAGE_VERSION
    assert _backend._core.__version__ == _backend.PACKAGE_VERSION
    assert synomosia.is_rust_backend() is True


def test_a_version_mismatch_is_refused_rather_than_tolerated():
    """The handshake has to be able to fail, or it is decoration."""
    original = _backend._RUST_VERSION
    try:
        _backend._RUST_VERSION = "0.0.0-not-a-real-build"
        with pytest.raises(synomosia.RustBackendUnavailable):
            synomosia.assert_rust_backend()
        assert synomosia.backend_report()["version_mismatch"] is not None
    finally:
        _backend._RUST_VERSION = original
    synomosia.assert_rust_backend()


# ---------------------------------------------------------------------------
# Parity with the Python the crate replaced
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/a",
        "https://example.com/path?q=1&r=2#frag",
        "",
        "https://example.com/caf\u00e9",        # non-ASCII, UTF-8 encoded
        "https://boards.4chan.org/x/thread/123",
    ],
)
def test_article_ids_match_hashlib_byte_for_byte(url):
    """The id is the articles table's primary key; it cannot drift.

    `_article_id` was `hashlib.sha256(url.encode()).hexdigest()[:16]`. If the
    Rust digest disagreed by one character, every article already stored would
    be re-inserted under a new id and the deduplication would quietly stop
    working.
    """
    expected = hashlib.sha256(url.encode()).hexdigest()[: _backend.ID_HEX_CHARS]
    assert synomosia.article_id(url) == expected


def test_the_id_length_constant_describes_the_ids_it_produces():
    assert len(synomosia.article_id("https://example.com")) == _backend.ID_HEX_CHARS


def test_html_normalisation_matches_the_passes_it_replaced():
    """Tags out, references decoded, whitespace collapsed -- in that order."""
    assert synomosia.strip_html("<p>Hidden &amp; buried</p>") == "Hidden & buried"
    assert synomosia.strip_html("&lt;b&gt;") == "<b>", (
        "tags are stripped before references are decoded, so an escaped tag "
        "survives as literal text"
    )
    assert synomosia.strip_html("  a \n\t b  ") == "a b"
    assert synomosia.strip_html("") == ""
    assert synomosia.strip_html("caf&eacute;") == "caf\u00e9"


def test_over_long_text_raises_instead_of_being_truncated():
    """A silent prefix would corrupt an article body without saying anything."""
    with pytest.raises(ValueError):
        synomosia.strip_html("a" * (_backend.MAX_TEXT_BYTES + 1))


def test_first_occurrences_keeps_the_first_of_each_duplicate_in_order():
    """`insert_articles` drops within-batch repeats through this.

    Syndicated stories arrive from several feeds at once. `INSERT OR IGNORE`
    already rejected the repeats, so the result must be identical -- what
    changes is that the repeats no longer cost two statements each.
    """
    keys = ["a", "b", "a", "c", "b", "a"]
    assert synomosia.first_occurrences(keys) == [0, 1, 3]
    assert synomosia.first_occurrences([]) == []
    assert synomosia.first_occurrences(["only"]) == [0]


def test_top_categories_counts_and_breaks_ties_by_first_appearance():
    """A stable tie order is what makes two reports over one day identical."""
    names = ["ufo", "finance", "ufo", "media", "finance", "ufo"]
    assert synomosia.top_categories(names, 2) == [("ufo", 3), ("finance", 2)]
    # "media" and "finance" would tie at one each if "finance" appeared once;
    # first appearance decides, so the order is the order they were seen.
    assert synomosia.top_categories(["b", "a"], 2) == [("b", 1), ("a", 1)]


def test_scoring_puts_a_title_prefix_above_a_title_mention_above_the_body():
    assert (
        synomosia.score_article("Moon landing", "", "moon")
        == _backend.SCORE_TITLE_PREFIX
    )
    assert (
        synomosia.score_article("The moon landing", "", "moon")
        == _backend.SCORE_TITLE_CONTAINS
    )
    assert (
        synomosia.score_article("Unrelated", "about the moon", "moon")
        == _backend.SCORE_CONTENT_CONTAINS
    )
    assert synomosia.score_article("Moon landing", "", "") == 0.0


def test_ranking_agrees_with_scoring_row_by_row():
    titles = ["Moon landing", "The moon landing", "Unrelated"]
    contents = ["", "", "about the moon"]
    ranked = synomosia.rank_articles(titles, contents, "moon", 10)
    assert [index for index, _score in ranked] == [0, 1, 2]
    for index, score in ranked:
        assert score == synomosia.score_article(titles[index], contents[index], "moon")


def test_keyword_extraction_ignores_stop_words_and_short_tokens():
    text = "the moon the moon landing was faked the landing"
    keywords = dict(synomosia.extract_keywords(text, ["the", "was"], 5))
    assert keywords["moon"] == 2
    assert keywords["landing"] == 2
    assert "the" not in keywords and "was" not in keywords


# ---------------------------------------------------------------------------
# The package's own export list
# ---------------------------------------------------------------------------

def test_every_name_in_all_resolves_and_appears_once():
    missing = [name for name in synomosia.__all__ if not hasattr(synomosia, name)]
    assert not missing, f"synomosia.__all__ names nothing: {missing}"
    duplicates = sorted(
        {name for name in synomosia.__all__ if synomosia.__all__.count(name) > 1}
    )
    assert not duplicates, f"synomosia.__all__ repeats {duplicates}"


def test_no_public_name_is_reachable_but_undeclared():
    """The other direction: `Refresh` was importable for a release without it.

    A name that is reachable as an attribute but absent from `__all__` is
    invisible to `from synomosia import *` and to every documentation tool
    that reads the list, which is how a public entry point disappears without
    anything failing.
    """
    import inspect

    exempt = {"annotations"}  # the __future__ feature object, not an export
    undeclared = sorted(
        name
        for name, value in vars(synomosia).items()
        if not name.startswith("_")
        and name not in set(synomosia.__all__)
        and name not in exempt
        and not inspect.ismodule(value)
    )
    assert not undeclared, (
        f"reachable as synomosia.<name> but missing from __all__: {undeclared}"
    )
