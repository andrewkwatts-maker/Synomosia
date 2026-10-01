//====== Augur/rust/augur_core/src/score.rs ======//
//! Relevance scoring for scraped articles.
//!
//! The scoring rule is deliberately crude and unchanged from the Python it
//! replaces -- a title prefix beats a title substring beats a body hit. What
//! changes is where the loop runs: [`rank_articles`] scores a whole day's
//! scrape and returns the ordered survivors, instead of Python calling
//! [`score_article`] once per article and sorting the results itself.

use crate::{check_sequence_len, check_text_len, CoreError};

/// Score awarded when the title begins with the query.
pub const SCORE_TITLE_PREFIX: f64 = 1000.0;
/// Score awarded when the title contains the query elsewhere.
pub const SCORE_TITLE_CONTAINS: f64 = 500.0;
/// Score added when the body contains the query.
pub const SCORE_CONTENT_CONTAINS: f64 = 100.0;

/// Score one article against a query. An empty query scores zero.
///
/// Case-insensitive: title, content and query are all lowercased first, which
/// is what the Python did and is why "NSA" matches "nsa".
pub fn score_article(title: &str, content: &str, query: &str) -> Result<f64, CoreError> {
    check_text_len(title)?;
    check_text_len(content)?;
    check_text_len(query)?;
    debug_assert!(
        title.len() <= crate::MAX_TEXT_BYTES && content.len() <= crate::MAX_TEXT_BYTES,
        "the length checks above reject anything larger"
    );
    if query.is_empty() {
        return Ok(0.0);
    }
    let needle = query.to_lowercase();
    debug_assert!(
        !needle.is_empty(),
        "an empty query returned above, and lowercasing cannot empty a string"
    );
    let hay_title = title.to_lowercase();
    let mut score = 0.0_f64;
    if hay_title.starts_with(&needle) {
        score += SCORE_TITLE_PREFIX;
    } else if hay_title.contains(&needle) {
        score += SCORE_TITLE_CONTAINS;
    }
    if content.to_lowercase().contains(&needle) {
        score += SCORE_CONTENT_CONTAINS;
    }
    debug_assert!(
        score >= 0.0 && score.is_finite(),
        "scores are finite and non-negative"
    );
    Ok(score)
}

/// Score every article and return the best `limit` as `(index, score)`.
///
/// Articles that score zero are dropped rather than returned with a zero, so
/// the caller cannot mistake "no match" for "matched weakly". Ties keep input
/// order, which makes the ranking reproducible across runs.
///
/// `titles` and `contents` are parallel; a length mismatch is an error, not a
/// silent truncation to the shorter of the two.
pub fn rank_articles(
    titles: &[String],
    contents: &[String],
    query: &str,
    limit: usize,
) -> Result<Vec<(usize, f64)>, CoreError> {
    check_sequence_len(titles.len())?;
    check_text_len(query)?;
    if titles.len() != contents.len() {
        return Err(CoreError::LengthMismatch {
            first: titles.len(),
            second: contents.len(),
        });
    }
    debug_assert!(
        titles.len() <= crate::MAX_SEQUENCE_LEN,
        "the sequence check above rejects anything longer"
    );
    debug_assert_eq!(titles.len(), contents.len(), "the pairing was just checked");

    let mut scored: Vec<(usize, f64)> = Vec::with_capacity(titles.len().min(limit.max(1)));
    // Bounded by the checked sequence length.
    for index in 0..titles.len() {
        let score = score_article(&titles[index], &contents[index], query)?;
        if score > 0.0 {
            scored.push((index, score));
        }
    }
    // `total_cmp` rather than `partial_cmp`: scores are finite by construction,
    // but a NaN slipping in must not make the comparator inconsistent and
    // panic the sort.
    scored.sort_by(|left, right| right.1.total_cmp(&left.1).then(left.0.cmp(&right.0)));
    scored.truncate(limit);
    Ok(scored)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn score(title: &str, content: &str, query: &str) -> f64 {
        score_article(title, content, query).expect("inputs are within the limits")
    }

    #[test]
    fn a_title_prefix_outranks_a_title_substring() {
        assert!(score("Deep State files", "", "deep") > score("The Deep State", "", "deep"));
    }

    #[test]
    fn body_hits_stack_on_title_hits() {
        assert_eq!(score("Deep State", "the deep state", "deep"), 1100.0);
        assert_eq!(score("Nothing", "the deep state", "deep"), 100.0);
    }

    #[test]
    fn an_empty_query_scores_zero_rather_than_matching_everything() {
        assert_eq!(score("anything", "anything", ""), 0.0);
    }

    #[test]
    fn matching_ignores_case_on_both_sides() {
        assert_eq!(score("MKULTRA", "", "mkultra"), SCORE_TITLE_PREFIX);
        assert_eq!(score("mkultra", "", "MKULTRA"), SCORE_TITLE_PREFIX);
    }

    #[test]
    fn ranking_orders_by_score_then_input_position() {
        let titles = vec![
            "unrelated".to_string(),
            "cabal watch".to_string(),
            "the cabal".to_string(),
            "cabal news".to_string(),
        ];
        let contents = vec![String::new(); 4];
        let ranked = rank_articles(&titles, &contents, "cabal", 10).expect("valid");
        assert_eq!(ranked[0].0, 1);
        assert_eq!(ranked[1].0, 3);
        assert_eq!(ranked[2].0, 2);
        assert_eq!(ranked.len(), 3, "the non-matching article is dropped");
    }

    #[test]
    fn ranking_respects_the_limit() {
        let titles = vec!["cabal a".to_string(), "cabal b".to_string()];
        let contents = vec![String::new(); 2];
        let ranked = rank_articles(&titles, &contents, "cabal", 1).expect("valid");
        assert_eq!(ranked.len(), 1);
    }

    #[test]
    fn mismatched_parallel_sequences_are_an_error() {
        let titles = vec!["a".to_string()];
        assert_eq!(
            rank_articles(&titles, &[], "q", 5),
            Err(CoreError::LengthMismatch {
                first: 1,
                second: 0
            })
        );
    }
}
