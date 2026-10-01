//====== Augur/rust/augur_core/src/keywords.rs ======//
//! Tokenisation and top-N keyword extraction over article text.
//!
//! The Python this replaces built a `dict` of counts one character at a time
//! (`"".join(c for c in word if c.isalpha())` allocates a generator, a list
//! and a string per token) and then sorted it. Two properties of that code
//! were wrong rather than merely slow, and are fixed here:
//!
//! 1. **Ties were nondeterministic in the Rust version.** It collected into a
//!    `HashMap` and sorted on count alone, so words with equal counts came out
//!    in hash order -- a different order on every process, and a different
//!    order from the Python fallback, which sorts stably. Extraction now
//!    breaks ties by first appearance, which is deterministic *and* matches
//!    Python's stable sort over insertion order.
//! 2. **The minimum length was measured in bytes.** `w.len() >= 3` admitted
//!    any two-character non-ASCII word, because two Cyrillic or Greek letters
//!    are four bytes. It is now a character count, as `len(w)` is in Python.

use std::collections::HashMap;

use crate::text::is_python_space;
use crate::{check_text_len, CoreError};

/// Shortest word that can become a keyword, in characters.
pub const MIN_KEYWORD_CHARS: usize = 3;

/// Running state for one word: how often it appeared and where first.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Tally {
    count: usize,
    first_seen: usize,
}

/// Strip non-alphabetic characters from a token and lowercase the rest.
///
/// Mirrors `"".join(c for c in word if c.isalpha()).lower()`. Returns `None`
/// when the result is too short to be a keyword, so the caller never allocates
/// a map entry for it.
fn normalise(token: &str) -> Option<String> {
    debug_assert!(!token.is_empty(), "the splitter never yields empty tokens");
    debug_assert!(
        token.len() <= crate::MAX_TEXT_BYTES,
        "a token cannot exceed the text it came from"
    );
    let mut chars = 0usize;
    let mut kept = String::with_capacity(token.len());
    for ch in token.chars() {
        if ch.is_alphabetic() {
            kept.push(ch);
            chars += 1;
        }
    }
    if chars < MIN_KEYWORD_CHARS {
        return None;
    }
    Some(kept.to_lowercase())
}

/// Split on whitespace exactly as Python's `str.split()` does.
///
/// `str::split_whitespace` would be the obvious choice but uses Rust's
/// `White_Space` property, which excludes U+001C..U+001F. Python splits on
/// those, so a feed payload containing one would tokenise differently.
fn tokens(text: &str) -> impl Iterator<Item = &str> {
    text.split(is_python_space).filter(|part| !part.is_empty())
}

/// Count words in `text`, returning the `top_n` most frequent as
/// `(word, count)` pairs.
///
/// Words shorter than [`MIN_KEYWORD_CHARS`] characters and words in
/// `stop_words` are ignored. Equal counts are ordered by first appearance.
pub fn extract_keywords(
    text: &str,
    stop_words: &[String],
    top_n: usize,
) -> Result<Vec<(String, usize)>, CoreError> {
    check_text_len(text)?;
    crate::check_sequence_len(stop_words.len())?;
    debug_assert!(
        text.len() <= crate::MAX_TEXT_BYTES,
        "the length check above rejects anything larger"
    );
    debug_assert!(
        stop_words.len() <= crate::MAX_SEQUENCE_LEN,
        "the sequence check above rejects anything longer"
    );

    let stop: std::collections::HashSet<&str> = stop_words.iter().map(String::as_str).collect();
    let mut tallies: HashMap<String, Tally> = HashMap::new();
    // The trip count is bounded by the text length, checked above: a token is
    // at least one byte, so there can be no more tokens than there are bytes.
    for (position, token) in tokens(text).enumerate() {
        let Some(word) = normalise(token) else {
            continue;
        };
        if stop.contains(word.as_str()) {
            continue;
        }
        tallies
            .entry(word)
            .and_modify(|tally| tally.count += 1)
            .or_insert(Tally {
                count: 1,
                first_seen: position,
            });
    }

    let mut pairs: Vec<(String, Tally)> = tallies.into_iter().collect();
    pairs.sort_unstable_by(|left, right| {
        right
            .1
            .count
            .cmp(&left.1.count)
            .then(left.1.first_seen.cmp(&right.1.first_seen))
    });
    pairs.truncate(top_n);
    Ok(pairs
        .into_iter()
        .map(|(word, tally)| (word, tally.count))
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn keywords(text: &str, top_n: usize) -> Vec<(String, usize)> {
        extract_keywords(text, &[], top_n).expect("input is within the limits")
    }

    #[test]
    fn counts_are_case_folded_and_punctuation_stripped() {
        // "deep-state;" loses its punctuation and becomes one word, so the
        // bare "Deep"/"DEEP!" pair is what collides.
        let got = keywords("Deep State, deep-state; DEEP!", 5);
        assert_eq!(got[0], ("deep".to_string(), 2));
        assert!(got.contains(&("deepstate".to_string(), 1)));
    }

    #[test]
    fn short_words_are_dropped_by_character_count_not_byte_count() {
        // Two Cyrillic letters are four bytes; the old byte test let them in.
        let got = keywords("\u{434}\u{430} \u{434}\u{430} conspiracy", 5);
        assert_eq!(got, vec![("conspiracy".to_string(), 1)]);
    }

    #[test]
    fn stop_words_are_removed() {
        let stop = vec!["the".to_string(), "and".to_string()];
        let got = extract_keywords("the cabal and the cabal", &stop, 5).expect("valid");
        assert_eq!(got, vec![("cabal".to_string(), 2)]);
    }

    #[test]
    fn ties_break_by_first_appearance_every_time() {
        let text = "zeta alpha beta gamma delta epsilon theta iota kappa";
        let first = keywords(text, 9);
        for _ in 0..32 {
            assert_eq!(keywords(text, 9), first, "tie order must be stable");
        }
        assert_eq!(first[0].0, "zeta");
        assert_eq!(first[1].0, "alpha");
    }

    #[test]
    fn top_n_truncates_after_sorting() {
        let got = keywords("aaa aaa bbb bbb bbb ccc", 1);
        assert_eq!(got, vec![("bbb".to_string(), 3)]);
    }

    #[test]
    fn separators_python_treats_as_space_split_tokens() {
        let got = keywords("alpha\u{1e}beta", 5);
        assert_eq!(got.len(), 2, "U+001E must split, not join");
    }

    #[test]
    fn oversized_text_is_an_error() {
        let big = "x".repeat(crate::MAX_TEXT_BYTES + 1);
        assert!(extract_keywords(&big, &[], 3).is_err());
    }
}
