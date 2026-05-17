use pyo3::prelude::*;
use std::collections::HashMap;

/// Extract top-N keywords from text, excluding stop words.
/// Returns list of (word, count) sorted by frequency descending.
#[pyfunction]
fn extract_keywords(text: &str, stop_words: Vec<String>, top_n: usize) -> Vec<(String, usize)> {
    let stop: std::collections::HashSet<String> = stop_words.into_iter().collect();
    let mut counts: HashMap<String, usize> = HashMap::new();
    for word in text.split_whitespace() {
        let w: String = word.chars()
            .filter(|c| c.is_alphabetic())
            .collect::<String>()
            .to_lowercase();
        if w.len() >= 3 && !stop.contains(&w) {
            *counts.entry(w).or_insert(0) += 1;
        }
    }
    let mut pairs: Vec<(String, usize)> = counts.into_iter().collect();
    pairs.sort_by(|a, b| b.1.cmp(&a.1));
    pairs.truncate(top_n);
    pairs
}

/// Score an article title + content against a query.
#[pyfunction]
fn score_article(title: &str, content: &str, query: &str) -> f64 {
    let q = query.to_lowercase();
    let t = title.to_lowercase();
    let c = content.to_lowercase();
    if q.is_empty() { return 0.0; }
    let mut score = 0.0_f64;
    if t.starts_with(&q)   { score += 1000.0; }
    else if t.contains(&q) { score += 500.0; }
    if c.contains(&q)      { score += 100.0; }
    score
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_keywords, m)?)?;
    m.add_function(wrap_pyfunction!(score_article, m)?)?;
    Ok(())
}
