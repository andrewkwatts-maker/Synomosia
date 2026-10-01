//====== Augur/rust/augur_core/src/pyfacade/report.rs ======//
//! Daily-report aggregation bindings.

use pyo3::prelude::*;

use crate::pyfacade::to_py_err;
use crate::report;

/// The `limit` most common categories as `(category, count)` pairs.
///
/// Ordered by descending count, ties by first appearance, so the sections of
/// two reports over the same day come out in the same order.
#[pyfunction]
fn top_categories(categories: Vec<String>, limit: usize) -> PyResult<Vec<(String, usize)>> {
    let ranked = report::top_categories(&categories, limit).map_err(to_py_err)?;
    debug_assert!(
        ranked.len() <= limit,
        "the result honours the requested size"
    );
    debug_assert!(
        ranked.iter().map(|(_, count)| count).sum::<usize>() <= categories.len(),
        "counts cannot exceed the number of articles counted"
    );
    Ok(ranked)
}

/// Attach this module's functions to the extension module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    debug_assert!(m.name().is_ok(), "the extension module has a name");
    debug_assert!(
        m.getattr("top_categories").is_err(),
        "registration must run exactly once"
    );
    m.add_function(wrap_pyfunction!(top_categories, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_busiest_category_leads() {
        let categories = vec!["ufo".to_string(), "cia".to_string(), "ufo".to_string()];
        let ranked = top_categories(categories, 5).expect("valid");
        assert_eq!(ranked[0], ("ufo".to_string(), 2));
    }

    #[test]
    fn an_empty_day_returns_an_empty_list_not_an_error() {
        assert!(top_categories(Vec::new(), 5).expect("valid").is_empty());
    }

    #[test]
    fn an_over_long_batch_raises() {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let many = vec!["x".to_string(); crate::MAX_SEQUENCE_LEN + 1];
            let err = top_categories(many, 5).expect_err("the limit applies");
            assert!(err.is_instance_of::<pyo3::exceptions::PyValueError>(py));
        });
    }
}
