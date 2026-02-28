"""tests/test_tokens.py — Hebrew tokenizer and Jaccard similarity tests.

Port of the implicit token logic tested in apps/worker/test/cluster.test.ts,
plus additional unit cases for the pure functions.
"""

from __future__ import annotations

import pytest

from cluster.tokens import HE_STOPWORDS, jaccard_similarity, tokenize


class TestTokenize:
    def test_empty_string_returns_empty(self):
        assert tokenize("") == frozenset()

    def test_basic_hebrew_tokenization(self):
        tokens = tokenize("שריפה גדולה בחיפה")
        assert "שריפה" in tokens
        assert "גדולה" in tokens
        assert "בחיפה" in tokens

    def test_stopwords_removed(self):
        # "עם" is a stopword
        tokens = tokenize("ביבי נפגש עם מנהיגים")
        assert "עם" not in tokens
        assert "ביבי" in tokens
        assert "נפגש" in tokens
        assert "מנהיגים" in tokens

    def test_short_tokens_removed(self):
        # Single-char tokens should be dropped
        tokens = tokenize("א ב ג שלום")
        assert "א" not in tokens
        assert "ב" not in tokens
        assert "ג" not in tokens
        assert "שלום" in tokens

    def test_punctuation_is_split_boundary(self):
        tokens = tokenize("שריפה, גדולה. בחיפה!")
        assert "שריפה" in tokens
        assert "גדולה" in tokens
        assert "בחיפה" in tokens

    def test_latin_lowercased(self):
        tokens = tokenize("Hello World")
        assert "hello" in tokens
        assert "world" in tokens
        assert "Hello" not in tokens

    def test_mixed_hebrew_latin(self):
        tokens = tokenize("מבצע IDF בגבול")
        assert "מבצע" in tokens
        assert "idf" in tokens

    def test_duplicate_words_deduped(self):
        tokens = tokenize("שריפה שריפה שריפה")
        assert len(tokens) == 1
        assert "שריפה" in tokens

    def test_stopword_set_has_73_unique_entries(self):
        assert len(HE_STOPWORDS) == 73

    def test_known_stopwords_present(self):
        for word in ["של", "את", "לא", "גם", "אבל", "כן", "הם", "הן"]:
            assert word in HE_STOPWORDS

    def test_all_stopwords_filtered(self):
        # Build a title from only stopwords — result should be empty
        stopword_title = " ".join(list(HE_STOPWORDS)[:10])
        tokens = tokenize(stopword_title)
        assert tokens == frozenset()

    def test_numbers_kept(self):
        tokens = tokenize("28 פברואר 2026")
        assert "28" in tokens
        assert "2026" in tokens

    def test_known_similar_pair_share_tokens(self):
        t1 = tokenize("ביבי נפגש עם מנהיגים אירופאים")
        t2 = tokenize("ביבי נפגש עם נשיאים אירופאים")
        shared = t1 & t2
        assert "ביבי" in shared
        assert "נפגש" in shared
        assert "אירופאים" in shared


class TestJaccardSimilarity:
    def test_both_empty_returns_one(self):
        assert jaccard_similarity(frozenset(), frozenset()) == 1.0

    def test_one_empty_returns_zero(self):
        assert jaccard_similarity(frozenset(["a"]), frozenset()) == 0.0
        assert jaccard_similarity(frozenset(), frozenset(["a"])) == 0.0

    def test_identical_sets_return_one(self):
        s = frozenset(["א", "ב", "ג"])
        assert jaccard_similarity(s, s) == 1.0

    def test_disjoint_sets_return_zero(self):
        a = frozenset(["שריפה", "חיפה"])
        b = frozenset(["רעידה", "תורכיה"])
        assert jaccard_similarity(a, b) == 0.0

    def test_partial_overlap(self):
        # |A|=4, |B|=4, |A∩B|={ג,ד}=2, |A∪B|=6 → 2/6 = 0.333...
        a = frozenset(["א", "ב", "ג", "ד"])
        b = frozenset(["ג", "ד", "ה", "ו"])
        result = jaccard_similarity(a, b)
        assert abs(result - 1 / 3) < 1e-9

    def test_known_similar_pair_exceeds_threshold(self):
        # ביבי titles: intersection={ביבי, נפגש, אירופאים}, union=5 → 3/5 = 0.6
        t1 = tokenize("ביבי נפגש עם מנהיגים אירופאים")
        t2 = tokenize("ביבי נפגש עם נשיאים אירופאים")
        score = jaccard_similarity(t1, t2)
        assert score > 0.25  # above clustering threshold

    def test_known_dissimilar_pair_below_threshold(self):
        t1 = tokenize("שריפה בחיפה")
        t2 = tokenize("רעידת אדמה בתורכיה")
        score = jaccard_similarity(t1, t2)
        assert score <= 0.25

    def test_symmetry(self):
        a = frozenset(["א", "ב", "ג"])
        b = frozenset(["ב", "ג", "ד"])
        assert jaccard_similarity(a, b) == jaccard_similarity(b, a)

    def test_formula_is_correct(self):
        # |A|=3, |B|=3, |A∩B|=1 → union=5, jaccard=1/5=0.2
        a = frozenset(["x", "y", "z"])
        b = frozenset(["z", "w", "v"])
        result = jaccard_similarity(a, b)
        assert abs(result - 1 / 5) < 1e-9
