//====== Augur/rust/augur_core/src/pyfacade/mod.rs ======//
//! PyO3 facade for the `synomosia` Python package.
//!
//! Gated behind the `python` feature so [`crate`] builds and tests standalone
//! with no interpreter on the path. **Rust does not depend on Python**: this
//! module is additive, and `augur_core` is a complete library without it.
//! Python is the thin wrapper, never the implementation.
//!
//! | Module | Surface |
//! |---|---|
//! | [`text`] | `strip_html` |
//! | [`keywords`] | `extract_keywords` |
//! | [`score`] | `score_article`, `rank_articles` |
//! | [`dedup`] | `article_id`, `first_occurrences` |
//! | [`report`] | `top_categories` |
//!
//! ## Conventions for everything under this directory
//!
//! - **Two runtime assertions minimum** per wrapper, checking what the
//!   boundary cannot express in types alone.
//! - **Bounded loops.** Every sequence from Python is length-checked in the
//!   core before iteration begins.
//! - **Errors surface as Python exceptions**, never as a default value. A
//!   wrapper that swallows an error is worse than one that does not exist,
//!   because it makes the backend look healthy while it is not.

// `#[pyfunction]` expands to a wrapper that converts the returned error into a
// `PyErr`. When the function already returns `PyResult`, that conversion is
// `PyErr -> PyErr`, and clippy flags the macro's own code as a useless
// conversion. The alternative is to stop returning `PyResult` from the
// wrappers, which would mean swallowing errors -- exactly what this facade
// exists to prevent. Fixed upstream in pyo3 0.23.
#![allow(clippy::useless_conversion)]

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::CoreError;

pub mod dedup;
pub mod keywords;
pub mod report;
pub mod score;
pub mod text;

/// Version this extension was compiled at.
///
/// `synomosia._backend.assert_rust_backend()` compares it with the Python
/// package version and refuses to run when they differ. A stale `_core.pyd`
/// left in the source tree from an earlier build is otherwise invisible and
/// produces behaviour that matches no version of the source.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Convert a core error into the Python exception it should raise.
///
/// Every variant is a caller mistake about size or shape, so `ValueError` is
/// right for all of them; the message carries the measured numbers.
pub fn to_py_err(error: CoreError) -> PyErr {
    debug_assert!(
        !error.to_string().is_empty(),
        "every error must describe itself"
    );
    debug_assert!(
        matches!(
            error,
            CoreError::TextTooLong { .. }
                | CoreError::SequenceTooLong { .. }
                | CoreError::LengthMismatch { .. }
        ),
        "all current variants map to ValueError; a new one needs a decision"
    );
    PyValueError::new_err(error.to_string())
}

/// True whenever this module is importable, which is the point: Python calls
/// it to confirm it is talking to the compiled backend and not to a stub.
#[pyfunction]
fn is_rust_backend() -> bool {
    true
}

/// Version handshake counterpart to `synomosia.__version__`.
#[pyfunction]
fn version_rust() -> &'static str {
    let segments = VERSION.split('.').count();
    debug_assert!(segments >= 2, "the version reads major.minor[.patch]");
    debug_assert!(
        VERSION.starts_with(|ch: char| ch.is_ascii_digit()),
        "the version starts with a numeric major component"
    );
    VERSION
}

/// `synomosia._core` module entry point. Maturin invokes this through the
/// `[tool.maturin] module-name` setting in `pyproject.toml`.
#[pymodule]
fn _core(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", VERSION)?;
    m.add("MAX_TEXT_BYTES", crate::MAX_TEXT_BYTES)?;
    m.add("MAX_SEQUENCE_LEN", crate::MAX_SEQUENCE_LEN)?;
    m.add_function(wrap_pyfunction!(is_rust_backend, m)?)?;
    m.add_function(wrap_pyfunction!(version_rust, m)?)?;
    text::register(m)?;
    keywords::register(m)?;
    score::register(m)?;
    dedup::register(m)?;
    report::register(m)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn errors_become_value_errors_carrying_the_numbers() {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let err = to_py_err(CoreError::TextTooLong { bytes: 9, limit: 4 });
            assert!(err.is_instance_of::<PyValueError>(py));
            let message = err.value_bound(py).to_string();
            assert!(message.contains('9') && message.contains('4'), "{message}");
        });
    }

    #[test]
    fn the_version_is_the_crate_version() {
        assert_eq!(version_rust(), env!("CARGO_PKG_VERSION"));
        assert!(is_rust_backend());
    }
}
