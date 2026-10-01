//====== Augur/rust/augur_core/src/report.rs ======//
//! Category histograms for the daily report.
//!
//! `generate_daily_report` used to build a `dict[str, list]` of whole article
//! dicts purely to take `len()` of each bucket and keep the five largest. That
//! is a full second copy of the day's scrape to answer a counting question.
//! Counting the category strings here answers it without moving the articles,
//! and pins the tie order, which a `dict`-order-dependent sort left implicit.

use std::collections::HashMap;

use crate::{check_sequence_len, CoreError};

/// Count each distinct category and return the `limit` largest.
///
/// Ordering is by descending count, then by first appearance -- the same order
/// Python's stable `sorted(..., reverse=True)` produced over an insertion
/// ordered dict, so the report sections do not shuffle between runs.
pub fn top_categories(
    categories: &[String],
    limit: usize,
) -> Result<Vec<(String, usize)>, CoreError> {
    check_sequence_len(categories.len())?;
    debug_assert!(
        categories.len() <= crate::MAX_SEQUENCE_LEN,
        "the sequence check above rejects anything longer"
    );
    debug_assert!(
        categories
            .iter()
            .all(|name| name.len() <= crate::MAX_TEXT_BYTES),
        "a category name cannot exceed the text limit"
    );

    let mut counts: HashMap<&str, (usize, usize)> = HashMap::new();
    // Bounded by the checked sequence length.
    for (position, name) in categories.iter().enumerate() {
        let slot = counts.entry(name.as_str()).or_insert((0, position));
        slot.0 += 1;
    }

    let mut ranked: Vec<(&str, (usize, usize))> = counts.into_iter().collect();
    ranked.sort_unstable_by(|left, right| {
        right.1 .0.cmp(&left.1 .0).then(left.1 .1.cmp(&right.1 .1))
    });
    ranked.truncate(limit);
    Ok(ranked
        .into_iter()
        .map(|(name, (count, _))| (name.to_string(), count))
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn categories(names: &[&str]) -> Vec<String> {
        names.iter().map(|name| (*name).to_string()).collect()
    }

    #[test]
    fn the_largest_bucket_comes_first() {
        let got = top_categories(&categories(&["ufo", "cia", "ufo"]), 5).expect("valid");
        assert_eq!(got[0], ("ufo".to_string(), 2));
        assert_eq!(got[1], ("cia".to_string(), 1));
    }

    #[test]
    fn ties_keep_first_appearance_order_on_every_run() {
        let names = categories(&["b", "a", "c", "d", "e", "f", "g"]);
        let first = top_categories(&names, 7).expect("valid");
        for _ in 0..32 {
            assert_eq!(top_categories(&names, 7).expect("valid"), first);
        }
        assert_eq!(first[0].0, "b");
    }

    #[test]
    fn the_limit_truncates_after_ranking() {
        let got = top_categories(&categories(&["a", "b", "b", "c"]), 1).expect("valid");
        assert_eq!(got, vec![("b".to_string(), 2)]);
    }

    #[test]
    fn an_empty_day_reports_nothing_rather_than_failing() {
        assert_eq!(top_categories(&[], 5).expect("valid"), Vec::new());
    }
}
