//====== Augur/rust/augur_core/src/pyfacade/score.rs ======//
//! Article scoring and ranking bindings.

use pyo3::prelude::*;

use crate::pyfacade::to_py_err;
use crate::score;

/// Score one article's title and content against a query.
///
/// An empty query scores `0.0`; there is no "match everything" mode.
#[pyfunction]
fn score_article(title: &str, content: &str, query: &str) -> PyResult<f64> {
    let value = score::score_article(title, content, query).map_err(to_py_err)?;
    debug_assert!(value.is_finite(), "a score is always a finite number");
    debug_assert!(
        value <= score::SCORE_TITLE_PREFIX + score::SCORE_CONTENT_CONTAINS,
        "the score cannot exceed the sum of its two components"
    );
    Ok(value)
}

/// Rank a batch of articles, returning `(index, score)` best first.
///
/// Only articles that actually match are returned, so an empty list means no
/// match rather than a list of zeroes. `titles` and `contents` must be the
/// same length; a mismatch raises `ValueError` instead of ranking the shorter
/// prefix and silently dropping the rest.
#[pyfunction]
fn rank_articles(
    titles: Vec<String>,
    contents: Vec<String>,
    query: &str,
    limit: usize,
) -> PyResult<Vec<(usize, f64)>> {
    let ranked = score::rank_articles(&titles, &contents, query, limit).map_err(to_py_err)?;
    debug_assert!(
        ranked.len() <= limit,
        "the result honours the requested size"
    );
    debug_assert!(
        ranked
            .iter()
            .all(|(index, value)| *index < titles.len() && *value > 0.0),
        "every result indexes a real article that matched"
    );
    Ok(ranked)
}

/// Attach this module's functions to the extension module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    debug_assert!(m.name().is_ok(), "the extension module has a name");
    debug_assert!(
        m.getattr("score_article").is_err(),
        "registration must run exactly once"
    );
    m.add_function(wrap_pyfunction!(score_article, m)?)?;
    m.add_function(wrap_pyfunction!(rank_articles, m)?)?;
    m.add("SCORE_TITLE_PREFIX", score::SCORE_TITLE_PREFIX)?;
    m.add("SCORE_TITLE_CONTAINS", score::SCORE_TITLE_CONTAINS)?;
    m.add("SCORE_CONTENT_CONTAINS", score::SCORE_CONTENT_CONTAINS)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scoring_crosses_the_boundary_unchanged() {
        assert_eq!(
            score_article("Deep State", "the deep state", "deep").expect("valid"),
            1100.0
        );
    }

    #[test]
    fn ranking_drops_non_matches_and_keeps_input_order_on_ties() {
        let titles = vec![
            "nothing".to_string(),
            "cabal one".to_string(),
            "cabal two".to_string(),
        ];
        let contents = vec![String::new(); 3];
        let ranked = rank_articles(titles, contents, "cabal", 10).expect("valid");
        assert_eq!(ranked, vec![(1, 1000.0), (2, 1000.0)]);
    }

    #[test]
    fn a_length_mismatch_raises_instead_of_truncating() {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let err = rank_articles(vec!["a".to_string()], Vec::new(), "a", 5)
                .expect_err("parallel sequences must match");
            assert!(err.is_instance_of::<pyo3::exceptions::PyValueError>(py));
        });
    }
}
