//====== Augur/rust/augur_core/src/pyfacade/text.rs ======//
//! HTML normalisation bindings.

use pyo3::prelude::*;

use crate::pyfacade::to_py_err;
use crate::text;

/// Remove HTML tags, decode character references and collapse whitespace.
///
/// Byte-for-byte equivalent to the three-pass Python it replaces; see
/// [`crate::text`] for the exact definition and the parity test that pins it.
///
/// Raises `ValueError` when the text exceeds `MAX_TEXT_BYTES` rather than
/// truncating it, because a silently shortened summary is indistinguishable
/// from a short article.
#[pyfunction]
fn strip_html(text: &str) -> PyResult<String> {
    let stripped = text::strip_html(text).map_err(to_py_err)?;
    debug_assert!(
        !stripped.contains("  "),
        "whitespace runs are collapsed to one space"
    );
    debug_assert!(
        !stripped.starts_with(' ') && !stripped.ends_with(' '),
        "the result is trimmed"
    );
    Ok(stripped)
}

/// Attach this module's functions to the extension module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    debug_assert!(m.name().is_ok(), "the extension module has a name");
    debug_assert!(
        m.getattr("strip_html").is_err(),
        "registration must run exactly once"
    );
    m.add_function(wrap_pyfunction!(strip_html, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tags_and_entities_are_removed_through_the_binding() {
        assert_eq!(
            strip_html("<p>caf&eacute;   &amp; bar</p>").expect("valid"),
            "caf\u{e9} & bar"
        );
    }

    #[test]
    fn an_over_long_input_raises_rather_than_truncating() {
        let big = "x".repeat(crate::MAX_TEXT_BYTES + 1);
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let err = strip_html(&big).expect_err("the limit must be enforced");
            assert!(err.is_instance_of::<pyo3::exceptions::PyValueError>(py));
        });
    }
}
