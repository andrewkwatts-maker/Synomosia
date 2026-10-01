//====== Augur/rust/augur_core/src/pyfacade/keywords.rs ======//
//! Keyword extraction bindings.

use pyo3::prelude::*;

use crate::keywords;
use crate::pyfacade::to_py_err;

/// Top-`top_n` keywords in `text` as `(word, count)`, most frequent first.
///
/// Words shorter than three *characters* and words in `stop_words` are
/// ignored. Equal counts are ordered by first appearance, so repeated calls
/// return the same list.
#[pyfunction]
fn extract_keywords(
    text: &str,
    stop_words: Vec<String>,
    top_n: usize,
) -> PyResult<Vec<(String, usize)>> {
    let found = keywords::extract_keywords(text, &stop_words, top_n).map_err(to_py_err)?;
    debug_assert!(
        found.len() <= top_n,
        "the result honours the requested size"
    );
    debug_assert!(
        found.windows(2).all(|pair| pair[0].1 >= pair[1].1),
        "counts are non-increasing"
    );
    Ok(found)
}

/// Attach this module's functions to the extension module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    debug_assert!(m.name().is_ok(), "the extension module has a name");
    debug_assert!(
        m.getattr("extract_keywords").is_err(),
        "registration must run exactly once"
    );
    m.add_function(wrap_pyfunction!(extract_keywords, m)?)?;
    m.add("MIN_KEYWORD_CHARS", keywords::MIN_KEYWORD_CHARS)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stop_words_arrive_as_a_python_list_and_are_applied() {
        let got =
            extract_keywords("the cabal and the cabal", vec!["the".to_string()], 5).expect("valid");
        assert_eq!(got[0], ("cabal".to_string(), 2));
        assert!(got.iter().all(|(word, _)| word != "the"));
    }

    #[test]
    fn requesting_zero_keywords_returns_nothing() {
        assert!(extract_keywords("cabal cabal", Vec::new(), 0)
            .expect("valid")
            .is_empty());
    }

    #[test]
    fn an_over_long_text_raises() {
        let big = "x".repeat(crate::MAX_TEXT_BYTES + 1);
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let err = extract_keywords(&big, Vec::new(), 3).expect_err("the limit applies");
            assert!(err.is_instance_of::<pyo3::exceptions::PyValueError>(py));
        });
    }
}
