//====== Augur/rust/augur_core/src/lib.rs ======//
//! `augur_core` -- the implementation behind the `synomosia` Python package.
//!
//! This crate does **not** depend on Python. The PyO3 bindings live in
//! [`pyfacade`] behind the additive `python` feature; everything below it is a
//! plain Rust library that builds, tests and benchmarks with no interpreter on
//! the path.
//!
//! ## What lives here
//!
//! The per-article hot path of the scraper, which runs once for every item
//! pulled from every feed, board and subreddit:
//!
//! | Module | Surface |
//! |---|---|
//! | [`text`] | `strip_html` -- tag removal, entity decoding, whitespace collapse |
//! | [`entities`] | the generated HTML character-reference tables |
//! | [`keywords`] | tokenisation and top-N keyword extraction |
//! | [`score`] | article scoring and batch ranking against a query |
//! | [`dedup`] | article ids (SHA-256) and first-occurrence deduplication |
//! | [`report`] | category histograms for the daily report |
//!
//! I/O, configuration, SQLite and the LLM calls stay in Python. They are
//! latency-bound on a socket or a disk, so moving them would buy nothing and
//! cost a great deal of binding surface.
//!
//! ## Conventions
//!
//! The project targets the NASA Power of Ten rules:
//!
//! - No recursion anywhere.
//! - Every loop has a bound that is checked before the loop runs. Callers
//!   supply text and sequences, so [`MAX_TEXT_BYTES`] and [`MAX_SEQUENCE_LEN`]
//!   are validated at the entry point of each public function.
//! - At least two meaningful `debug_assert!` per function.
//! - No discarded `Result`. Failures return [`CoreError`] and reach Python as
//!   an exception -- never as an empty list or a zero score, because a wrapper
//!   that swallows an error makes a broken backend look healthy.

use core::fmt;

pub mod dedup;
pub mod entities;
pub mod keywords;
pub mod report;
pub mod score;
pub mod text;

#[cfg(feature = "python")]
pub mod pyfacade;

/// Largest text accepted by any single call, in bytes (4 MiB).
///
/// Feed summaries are truncated to 3,000 characters and 4chan comments are
/// smaller still, so this is roughly a thousand times the real working size.
/// It exists to give every character loop a bound that is checked up front.
pub const MAX_TEXT_BYTES: usize = 4 * 1024 * 1024;

/// Largest sequence accepted by any single call, in elements.
///
/// A day's scrape is a few thousand articles. As with [`MAX_TEXT_BYTES`], the
/// point is a checked bound rather than a realistic ceiling.
pub const MAX_SEQUENCE_LEN: usize = 1_048_576;

/// Everything that can go wrong in this crate.
///
/// Deliberately small and total: each variant carries the numbers a caller
/// needs to fix the call, so the Python side can raise a message that names
/// the offending size rather than "invalid input".
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CoreError {
    /// Text longer than [`MAX_TEXT_BYTES`].
    TextTooLong { bytes: usize, limit: usize },
    /// Sequence longer than [`MAX_SEQUENCE_LEN`].
    SequenceTooLong { len: usize, limit: usize },
    /// Two sequences that must be parallel were not the same length.
    LengthMismatch { first: usize, second: usize },
}

impl fmt::Display for CoreError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CoreError::TextTooLong { bytes, limit } => {
                write!(f, "text of {bytes} bytes exceeds the {limit}-byte limit")
            }
            CoreError::SequenceTooLong { len, limit } => {
                write!(f, "sequence of {len} items exceeds the {limit}-item limit")
            }
            CoreError::LengthMismatch { first, second } => {
                write!(
                    f,
                    "parallel sequences differ in length: {first} vs {second}"
                )
            }
        }
    }
}

impl std::error::Error for CoreError {}

/// Reject text that would give a character loop an unbounded trip count.
///
/// Called first by every public function that walks a string, so the bound is
/// established before any iteration begins rather than checked inside it.
pub fn check_text_len(text: &str) -> Result<(), CoreError> {
    let bytes = text.len();
    debug_assert!(
        bytes >= text.chars().count(),
        "UTF-8 uses at least one byte per character"
    );
    debug_assert!(
        bytes <= isize::MAX as usize,
        "string length must fit an isize"
    );
    if bytes > MAX_TEXT_BYTES {
        return Err(CoreError::TextTooLong {
            bytes,
            limit: MAX_TEXT_BYTES,
        });
    }
    Ok(())
}

/// Reject a caller-supplied sequence that would give a loop an unbounded
/// trip count. Mirrors [`check_text_len`] for the batch entry points.
pub fn check_sequence_len(len: usize) -> Result<(), CoreError> {
    debug_assert!(len <= isize::MAX as usize, "length must fit an isize");
    debug_assert!(
        len.checked_mul(core::mem::size_of::<usize>()).is_some(),
        "an index list for this sequence must be addressable"
    );
    if len > MAX_SEQUENCE_LEN {
        return Err(CoreError::SequenceTooLong {
            len,
            limit: MAX_SEQUENCE_LEN,
        });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn text_within_the_limit_is_accepted() {
        assert_eq!(check_text_len("conspiracy"), Ok(()));
        assert_eq!(check_text_len(""), Ok(()));
    }

    #[test]
    fn oversized_text_is_rejected_with_the_measurements() {
        let big = "x".repeat(MAX_TEXT_BYTES + 1);
        assert_eq!(
            check_text_len(&big),
            Err(CoreError::TextTooLong {
                bytes: MAX_TEXT_BYTES + 1,
                limit: MAX_TEXT_BYTES,
            })
        );
    }

    #[test]
    fn oversized_sequences_are_rejected() {
        assert_eq!(check_sequence_len(MAX_SEQUENCE_LEN), Ok(()));
        assert!(check_sequence_len(MAX_SEQUENCE_LEN + 1).is_err());
    }

    #[test]
    fn errors_name_the_offending_size() {
        let msg = CoreError::LengthMismatch {
            first: 3,
            second: 4,
        }
        .to_string();
        assert!(msg.contains('3') && msg.contains('4'), "{msg}");
    }
}
