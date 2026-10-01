"""Type stubs for the compiled `augur_core` extension.

Every symbol here is implemented in Rust (rust/augur_core). Errors are raised,
never returned as a default: each function raises `ValueError` when an input
exceeds `MAX_TEXT_BYTES` or `MAX_SEQUENCE_LEN`, or when parallel sequences
disagree in length.
"""

__version__: str

MAX_TEXT_BYTES: int
MAX_SEQUENCE_LEN: int
MIN_KEYWORD_CHARS: int
ID_HEX_CHARS: int
SCORE_TITLE_PREFIX: float
SCORE_TITLE_CONTAINS: float
SCORE_CONTENT_CONTAINS: float

def is_rust_backend() -> bool: ...
def version_rust() -> str: ...
def strip_html(text: str) -> str: ...
def extract_keywords(
    text: str, stop_words: list[str], top_n: int
) -> list[tuple[str, int]]: ...
def score_article(title: str, content: str, query: str) -> float: ...
def rank_articles(
    titles: list[str], contents: list[str], query: str, limit: int
) -> list[tuple[int, float]]: ...
def article_id(url: str) -> str: ...
def first_occurrences(keys: list[str]) -> list[int]: ...
def top_categories(categories: list[str], limit: int) -> list[tuple[str, int]]: ...
