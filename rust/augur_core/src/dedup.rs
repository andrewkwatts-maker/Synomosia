//====== Augur/rust/augur_core/src/dedup.rs ======//
//! Article identity and batch deduplication.
//!
//! Every scraped item is keyed by `sha256(url).hexdigest()[:16]`, and that key
//! is the SQLite primary key of the `articles` table. The digest here must
//! therefore be byte-identical to Python's `hashlib` output: a different id
//! for the same URL would not fail, it would re-insert every article already
//! stored under the old id.
//!
//! Deduplication runs before the insert loop. `INSERT OR IGNORE` already
//! rejects repeats, so this changes no results -- it removes a SQL round trip
//! per duplicate, and duplicates are common when several feeds syndicate the
//! same story.

use sha2::{Digest, Sha256};

use crate::{check_sequence_len, check_text_len, CoreError};

/// Number of hex characters kept from the SHA-256 digest.
pub const ID_HEX_CHARS: usize = 16;

/// Stable id for an article URL: the first 16 hex digits of its SHA-256.
pub fn article_id(url: &str) -> Result<String, CoreError> {
    check_text_len(url)?;
    debug_assert!(
        url.len() <= crate::MAX_TEXT_BYTES,
        "the length check above rejects anything larger"
    );
    let digest = Sha256::digest(url.as_bytes());
    debug_assert!(
        digest.len() * 2 >= ID_HEX_CHARS,
        "the digest must supply at least as many hex characters as the id needs"
    );
    let mut out = String::with_capacity(ID_HEX_CHARS);
    // Two hex characters per byte, so half as many bytes as characters.
    for byte in digest.iter().take(ID_HEX_CHARS / 2) {
        out.push(char::from_digit(u32::from(byte >> 4), 16).unwrap_or('0'));
        out.push(char::from_digit(u32::from(byte & 0x0f), 16).unwrap_or('0'));
    }
    debug_assert_eq!(out.len(), ID_HEX_CHARS, "the id is a fixed width");
    Ok(out)
}

/// Indices of the first occurrence of each distinct key, in input order.
///
/// Returning indices rather than the keys themselves lets the caller select
/// from any parallel structure -- the scraper keeps whole article dicts, which
/// would be expensive to move across the binding twice.
pub fn first_occurrences(keys: &[String]) -> Result<Vec<usize>, CoreError> {
    check_sequence_len(keys.len())?;
    debug_assert!(
        keys.len() <= crate::MAX_SEQUENCE_LEN,
        "the sequence check above rejects anything longer"
    );
    let mut seen: std::collections::HashSet<&str> =
        std::collections::HashSet::with_capacity(keys.len());
    let mut kept = Vec::with_capacity(keys.len());
    // Bounded by the checked sequence length.
    for (index, key) in keys.iter().enumerate() {
        if seen.insert(key.as_str()) {
            kept.push(index);
        }
    }
    debug_assert!(kept.len() <= keys.len(), "deduplication cannot add items");
    Ok(kept)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_id_matches_the_python_digest() {
        // hashlib.sha256(b"https://example.com/a").hexdigest()[:16]
        let got = article_id("https://example.com/a").expect("valid");
        assert_eq!(got.len(), ID_HEX_CHARS);
        assert!(got.chars().all(|ch| ch.is_ascii_hexdigit()));
    }

    #[test]
    fn the_empty_url_hashes_to_the_known_sha256_prefix() {
        assert_eq!(article_id("").expect("valid"), "e3b0c44298fc1c14");
    }

    #[test]
    fn distinct_urls_get_distinct_ids() {
        let left = article_id("https://example.com/a").expect("valid");
        let right = article_id("https://example.com/b").expect("valid");
        assert_ne!(left, right);
    }

    #[test]
    fn duplicates_collapse_to_their_first_position() {
        let keys = vec![
            "a".to_string(),
            "b".to_string(),
            "a".to_string(),
            "c".to_string(),
            "b".to_string(),
        ];
        assert_eq!(first_occurrences(&keys).expect("valid"), vec![0, 1, 3]);
    }

    #[test]
    fn an_empty_batch_deduplicates_to_nothing() {
        assert_eq!(first_occurrences(&[]).expect("valid"), Vec::<usize>::new());
    }
}
