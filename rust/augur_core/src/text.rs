//====== Augur/rust/augur_core/src/text.rs ======//
//! HTML normalisation: the single hottest path in the scraper.
//!
//! [`strip_html`] runs once per 4chan thread and once per feed entry, over
//! summaries up to 3,000 characters. In Python it was three passes of
//! `re.sub` plus `html.unescape`, each allocating a fresh string.
//!
//! The output is defined to be exactly what this Python produced:
//!
//! ```python
//! text = re.sub(r"<[^>]+>", " ", text)
//! text = html.unescape(text)
//! text = re.sub(r"\s+", " ", text).strip()
//! ```
//!
//! "Exactly" is load-bearing. The result is stored as the article summary and
//! indexed into FTS5, so a divergence would not raise anything -- it would
//! quietly change what the corpus says. `tests/test_rust_core.py` therefore
//! sweeps all 2,231 HTML entities and every Unicode scalar against CPython.

use crate::entities::{INVALID_CHARREFS, INVALID_CODEPOINTS, MAX_ENTITY_NAME_CHARS, NAMED_REFS};
use crate::{check_text_len, CoreError};

/// Replacement character used for numeric references outside Unicode.
const REPLACEMENT: char = '\u{fffd}';

/// Any numeric reference at or above this is out of range; the scanner clamps
/// here so an arbitrarily long digit run cannot overflow the accumulator.
const ABOVE_UNICODE_MAX: u32 = 0x11_0000;

/// `\s` as Python's `re` module defines it for `str` patterns.
///
/// Rust's `char::is_whitespace` follows the Unicode `White_Space` property,
/// which omits the four file/group/record/unit separators U+001C..U+001F.
/// Python matches them, and they occur in real feed payloads, so leaving them
/// out would silently stop collapsing them.
#[inline]
pub fn is_python_space(ch: char) -> bool {
    ch.is_whitespace() || matches!(ch, '\u{1c}'..='\u{1f}')
}

/// True for characters the named-entity alternative of Python's charref
/// pattern accepts: `[^\t\n\f <&#;]`.
#[inline]
fn is_entity_name_char(ch: char) -> bool {
    !matches!(ch, '\t' | '\n' | '\u{c}' | ' ' | '<' | '&' | '#' | ';')
}

/// Byte index just past the `>` closing a `<[^>]+>` tag that starts at `lt`.
///
/// `search_from` is a forward-only cursor into the input. Restarting the `>`
/// search from the beginning for each `<` would make a run of `<<<<...`
/// quadratic; because the cursor never moves backwards, the total work across
/// a whole document stays linear in its length.
fn tag_end(input: &str, lt: usize, search_from: &mut usize) -> Option<usize> {
    debug_assert!(lt < input.len(), "the `<` must be inside the input");
    debug_assert!(
        input.is_char_boundary(lt),
        "the `<` must start on a char boundary"
    );
    let start = if *search_from > lt + 1 {
        *search_from
    } else {
        lt + 1
    };
    if start >= input.len() {
        *search_from = input.len();
        return None;
    }
    match input[start..].find('>') {
        // `[^>]+` needs at least one character, so `<>` is not a tag.
        Some(offset) => {
            let gt = start + offset;
            *search_from = gt + 1;
            if gt > lt + 1 {
                Some(gt + 1)
            } else {
                None
            }
        }
        None => {
            // No `>` remains anywhere, so no later `<` can close either.
            *search_from = input.len();
            None
        }
    }
}

/// Replace every `<[^>]+>` with a single space, appending to an empty `out`.
pub fn strip_tags(input: &str, out: &mut String) {
    debug_assert!(
        input.len() <= crate::MAX_TEXT_BYTES,
        "caller checked the bound"
    );
    debug_assert!(out.is_empty(), "output buffer starts empty");
    let mut skip_to = 0usize;
    let mut search_from = 0usize;
    for (idx, ch) in input.char_indices() {
        if idx < skip_to {
            continue;
        }
        if ch == '<' {
            if let Some(end) = tag_end(input, idx, &mut search_from) {
                out.push(' ');
                skip_to = end;
                continue;
            }
        }
        out.push(ch);
    }
}

/// Resolve a numeric character reference, following the same four rules and
/// the same order as CPython's `html._replace_charref`.
fn numeric_replacement(value: u32, out: &mut String) {
    debug_assert!(value <= ABOVE_UNICODE_MAX, "the scanner clamps the value");
    debug_assert!(!INVALID_CHARREFS.is_empty(), "the remap table is generated");
    if let Ok(idx) = INVALID_CHARREFS.binary_search_by(|probe| probe.0.cmp(&value)) {
        out.push_str(INVALID_CHARREFS[idx].1);
        return;
    }
    if (0xd800..=0xdfff).contains(&value) || value > 0x10_ffff {
        out.push(REPLACEMENT);
        return;
    }
    if INVALID_CODEPOINTS.binary_search(&value).is_ok() {
        return;
    }
    // Surrogates and out-of-range values were rejected above, so this cannot
    // fail; fall back loudly rather than unwrapping.
    match char::from_u32(value) {
        Some(ch) => out.push(ch),
        None => {
            debug_assert!(
                false,
                "value {value} passed the range checks yet is not a char"
            );
            out.push(REPLACEMENT);
        }
    }
}

/// Scan `#...` after an `&`. Returns bytes consumed (including the `#`).
fn numeric_charref(body: &str, out: &mut String) -> Option<usize> {
    debug_assert!(
        body.len() <= crate::MAX_TEXT_BYTES,
        "caller checked the bound"
    );
    debug_assert!(
        body.is_char_boundary(0),
        "the body must start on a char boundary"
    );
    let hex = matches!(body.chars().next(), Some('x') | Some('X'));
    let skip = usize::from(hex);
    let radix = if hex { 16 } else { 10 };
    let digits = &body[skip..];

    let mut consumed = 0usize;
    let mut seen = 0usize;
    let mut value: u32 = 0;
    for ch in digits.chars() {
        match ch.to_digit(radix) {
            Some(digit) => {
                value = value.saturating_mul(radix).saturating_add(digit);
                // Clamp so an arbitrarily long digit run stays in range; every
                // value above the Unicode maximum decodes identically anyway.
                value = value.min(ABOVE_UNICODE_MAX);
                consumed += ch.len_utf8();
                seen += 1;
            }
            None => break,
        }
    }
    if seen == 0 {
        return None;
    }
    let semi = usize::from(digits[consumed..].starts_with(';'));
    numeric_replacement(value, out);
    Some(skip + consumed + semi)
}

/// Look up a named reference, applying the standard's longest-prefix rule.
///
/// Writes the replacement to `out` and returns `true`, or leaves `out`
/// untouched and returns `false` when no prefix of `name` is a known entity.
fn named_replacement(name: &str, out: &mut String) -> bool {
    debug_assert!(!name.is_empty(), "the scanner rejects an empty name");
    debug_assert!(
        name.chars().count() <= MAX_ENTITY_NAME_CHARS + 1,
        "the scanner bounds the name at 32 chars plus an optional `;`"
    );
    if let Ok(idx) = NAMED_REFS.binary_search_by(|probe| probe.0.cmp(name)) {
        out.push_str(NAMED_REFS[idx].1);
        return true;
    }
    // Byte offset at which each character starts, so prefixes can be taken by
    // character count the way CPython takes them.
    let mut starts = [0usize; MAX_ENTITY_NAME_CHARS + 2];
    let mut count = 0usize;
    for (idx, _) in name.char_indices() {
        if count >= starts.len() {
            break;
        }
        starts[count] = idx;
        count += 1;
    }
    for chars in (2..count).rev() {
        let cut = starts[chars];
        if let Ok(idx) = NAMED_REFS.binary_search_by(|probe| probe.0.cmp(&name[..cut])) {
            out.push_str(NAMED_REFS[idx].1);
            out.push_str(&name[cut..]);
            return true;
        }
    }
    false
}

/// Scan a named reference after an `&`. Returns bytes consumed.
fn named_charref(rest: &str, out: &mut String) -> Option<usize> {
    debug_assert!(
        rest.len() <= crate::MAX_TEXT_BYTES,
        "caller checked the bound"
    );
    let mut consumed = 0usize;
    let mut seen = 0usize;
    for ch in rest.chars() {
        if seen >= MAX_ENTITY_NAME_CHARS || !is_entity_name_char(ch) {
            break;
        }
        consumed += ch.len_utf8();
        seen += 1;
    }
    debug_assert!(
        seen <= MAX_ENTITY_NAME_CHARS,
        "the scanner stops at the name-length bound"
    );
    if seen == 0 {
        return None;
    }
    let semi = usize::from(rest[consumed..].starts_with(';'));
    let name = &rest[..consumed + semi];
    if named_replacement(name, out) {
        Some(consumed + semi)
    } else {
        None
    }
}

/// Decode HTML character references, appending to an empty `out`.
///
/// Equivalent to `html.unescape`. When no reference matches at an `&`, the
/// `&` is emitted and scanning resumes at the next character -- which is what
/// CPython's regex does, because neither `&` nor `#` can appear inside a name.
pub fn unescape(input: &str, out: &mut String) {
    debug_assert!(
        input.len() <= crate::MAX_TEXT_BYTES,
        "caller checked the bound"
    );
    debug_assert!(out.is_empty(), "output buffer starts empty");
    let mut skip_to = 0usize;
    for (idx, ch) in input.char_indices() {
        if idx < skip_to {
            continue;
        }
        if ch != '&' {
            out.push(ch);
            continue;
        }
        let rest = &input[idx + 1..];
        let consumed = match rest.strip_prefix('#') {
            Some(body) => numeric_charref(body, out).map(|used| used + 1),
            None => named_charref(rest, out),
        };
        match consumed {
            Some(used) => skip_to = idx + 1 + used,
            None => out.push('&'),
        }
    }
}

/// Collapse runs of whitespace to a single space and trim the ends,
/// appending to an empty `out`.
///
/// Equivalent to `re.sub(r"\s+", " ", text).strip()`.
pub fn collapse_whitespace(input: &str, out: &mut String) {
    debug_assert!(
        input.len() <= crate::MAX_TEXT_BYTES,
        "caller checked the bound"
    );
    debug_assert!(out.is_empty(), "output buffer starts empty");
    let mut pending = false;
    let mut wrote = false;
    for ch in input.chars() {
        if is_python_space(ch) {
            // Leading whitespace is dropped rather than remembered, which is
            // what makes the trailing `.strip()` unnecessary.
            pending = wrote;
            continue;
        }
        if pending {
            out.push(' ');
            pending = false;
        }
        out.push(ch);
        wrote = true;
    }
}

/// Remove HTML tags, decode entities and normalise whitespace.
///
/// The three stages must stay in this order: `&lt;b&gt;` has to survive tag
/// removal and become literal `<b>` text, not be stripped as markup.
pub fn strip_html(input: &str) -> Result<String, CoreError> {
    check_text_len(input)?;
    debug_assert!(
        input.len() <= crate::MAX_TEXT_BYTES,
        "the length check above rejects anything larger"
    );
    if input.is_empty() {
        return Ok(String::new());
    }
    let mut tagless = String::with_capacity(input.len());
    strip_tags(input, &mut tagless);
    let mut decoded = String::with_capacity(tagless.len());
    unescape(&tagless, &mut decoded);
    let mut out = String::with_capacity(decoded.len());
    collapse_whitespace(&decoded, &mut out);
    debug_assert!(
        !out.starts_with(is_python_space) && !out.ends_with(is_python_space),
        "the result is trimmed"
    );
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn strip(input: &str) -> String {
        strip_html(input).expect("input is within the length limit")
    }

    #[test]
    fn tags_become_a_single_space() {
        assert_eq!(strip("<p>hello</p><p>world</p>"), "hello world");
    }

    #[test]
    fn an_unclosed_angle_bracket_is_literal() {
        assert_eq!(strip("a < b"), "a < b");
        assert_eq!(strip("<>"), "<>");
    }

    #[test]
    fn named_entities_decode() {
        assert_eq!(strip("caf&eacute; &amp; bar"), "caf\u{e9} & bar");
        // No semicolon: the html5 table carries both forms.
        assert_eq!(strip("A&ampB"), "A&B");
    }

    #[test]
    fn the_longest_known_prefix_wins() {
        // `&notit;` is not an entity, but `&not` is, so the tail stays.
        assert_eq!(strip("&notit;"), "\u{ac}it;");
    }

    #[test]
    fn unknown_references_are_left_alone() {
        assert_eq!(strip("&nosuchthing;"), "&nosuchthing;");
        assert_eq!(strip("bare & ampersand"), "bare & ampersand");
    }

    #[test]
    fn numeric_references_decode_in_both_bases() {
        assert_eq!(strip("&#65;&#x42;&#X43"), "ABC");
    }

    #[test]
    fn windows_1252_refs_are_remapped_and_noncharacters_vanish() {
        assert_eq!(strip("&#151;"), "\u{2014}");
        assert_eq!(strip("a&#xFFFE;b"), "ab");
        assert_eq!(strip("&#xD800;"), "\u{fffd}");
    }

    #[test]
    fn an_absurdly_long_digit_run_does_not_overflow() {
        let many = format!("&#{}65;", "0".repeat(64));
        assert_eq!(strip(&many), "A");
        let huge = format!("&#{};", "9".repeat(64));
        assert_eq!(strip(&huge), "\u{fffd}");
    }

    #[test]
    fn tag_scanning_stays_linear_on_pathological_input() {
        let many = "<".repeat(20_000);
        assert_eq!(strip(&many).len(), 20_000);
    }

    #[test]
    fn whitespace_collapses_and_trims() {
        assert_eq!(strip("  a\t\n b \u{1c}c  "), "a b c");
    }

    #[test]
    fn oversized_input_is_an_error_not_a_truncation() {
        let big = "x".repeat(crate::MAX_TEXT_BYTES + 1);
        assert!(matches!(
            strip_html(&big),
            Err(CoreError::TextTooLong { .. })
        ));
    }
}
