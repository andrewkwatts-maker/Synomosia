//====== Augur/rust/augur_core/src/pyfacade/dedup.rs ======//
//! Article identity and deduplication bindings.

use pyo3::prelude::*;

use crate::dedup;
use crate::pyfacade::to_py_err;

/// Stable article id: the first 16 hex digits of `sha256(url)`.
///
/// Identical to `hashlib.sha256(url.encode()).hexdigest()[:16]`. This is the
/// primary key of the `articles` table, so the two must never diverge.
#[pyfunction]
fn article_id(url: &str) -> PyResult<String> {
    let id = dedup::article_id(url).map_err(to_py_err)?;
    debug_assert_eq!(id.len(), dedup::ID_HEX_CHARS, "ids are a fixed width");
    debug_assert!(
        id.chars().all(|ch| ch.is_ascii_hexdigit()),
        "ids are lowercase hex"
    );
    Ok(id)
}

/// Indices of the first occurrence of each distinct key, in input order.
///
/// The caller keeps the articles; only their keys cross the boundary.
#[pyfunction]
fn first_occurrences(keys: Vec<String>) -> PyResult<Vec<usize>> {
    let kept = dedup::first_occurrences(&keys).map_err(to_py_err)?;
    debug_assert!(kept.len() <= keys.len(), "deduplication cannot add items");
    debug_assert!(
        kept.windows(2).all(|pair| pair[0] < pair[1]),
        "indices come back in strictly increasing input order"
    );
    Ok(kept)
}

/// Attach this module's functions to the extension module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    debug_assert!(m.name().is_ok(), "the extension module has a name");
    debug_assert!(
        m.getattr("article_id").is_err(),
        "registration must run exactly once"
    );
    m.add_function(wrap_pyfunction!(article_id, m)?)?;
    m.add_function(wrap_pyfunction!(first_occurrences, m)?)?;
    m.add("ID_HEX_CHARS", dedup::ID_HEX_CHARS)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_empty_url_matches_the_known_digest_prefix() {
        assert_eq!(article_id("").expect("valid"), "e3b0c44298fc1c14");
    }

    #[test]
    fn repeated_keys_keep_only_their_first_index() {
        let keys = vec!["a".to_string(), "a".to_string(), "b".to_string()];
        assert_eq!(first_occurrences(keys).expect("valid"), vec![0, 2]);
    }

    #[test]
    fn an_over_long_url_raises() {
        let big = "x".repeat(crate::MAX_TEXT_BYTES + 1);
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let err = article_id(&big).expect_err("the limit applies");
            assert!(err.is_instance_of::<pyo3::exceptions::PyValueError>(py));
        });
    }
}
