import unittest

from caption_stream import (
    CATCH_UP_BACKLOG,
    MAX_BATCH_MS,
    MAX_INTERVAL_MS,
    MIN_INTERVAL_MS,
    CaptionStream,
    WordPacer,
    new_words,
)


class NewWordsTest(unittest.TestCase):
    def test_no_previous_caption(self):
        self.assertEqual(new_words([], "Hello there"), ["Hello", "there"])

    def test_partial_overlap(self):
        previous = "we went to the market yesterday".split()
        self.assertEqual(
            new_words(previous, "the market yesterday and bought bread"),
            ["and", "bought", "bread"],
        )

    def test_full_overlap(self):
        previous = "we went to the market".split()
        self.assertEqual(new_words(previous, "to the market"), [])

    def test_no_overlap(self):
        previous = "good morning everyone".split()
        self.assertEqual(new_words(previous, "Let us begin"), ["Let", "us", "begin"])

    def test_ignores_case_and_punctuation(self):
        previous = "I think, it is Raining.".split()
        self.assertEqual(
            new_words(previous, "it is raining, so stay home"),
            ["so", "stay", "home"],
        )

    def test_short_single_word_is_not_overlap(self):
        previous = "he opened the".split()
        self.assertEqual(new_words(previous, "the door"), ["the", "door"])

    def test_long_single_word_is_overlap(self):
        previous = "we visited Kyiv".split()
        self.assertEqual(new_words(previous, "Kyiv in spring"), ["in", "spring"])

    def test_prefers_longest_overlap(self):
        previous = "very very good".split()
        self.assertEqual(new_words(previous, "very good news"), ["news"])

    def test_ignores_punctuation_only_tokens_in_previous(self):
        previous = "we went to the market ...".split()
        self.assertEqual(
            new_words(previous, "the market and bought"), ["and", "bought"]
        )

    def test_ignores_punctuation_only_tokens_in_caption(self):
        previous = "he said hello".split()
        self.assertEqual(new_words(previous, "- hello there"), ["there"])

    def test_drops_leading_punctuation_only_tokens(self):
        previous = "we went to the market".split()
        self.assertEqual(
            new_words(previous, "the market — and bought"), ["and", "bought"]
        )
        self.assertEqual(new_words([], "... so then"), ["so", "then"])

    def test_overlap_is_capped(self):
        words = [f"word{i}" for i in range(12)]
        caption = " ".join(words + ["next"])
        # Longer than the cap, so it is treated as new text.
        self.assertEqual(new_words(words, caption), caption.split())


class CaptionStreamTest(unittest.TestCase):
    def test_tracks_previous_caption(self):
        stream = CaptionStream()
        self.assertEqual(stream.push("one two three"), ["one", "two", "three"])
        self.assertEqual(stream.push("two three four"), ["four"])
        self.assertEqual(stream.push("three four five six"), ["five", "six"])

    def test_empty_caption_keeps_previous(self):
        stream = CaptionStream()
        stream.push("we went to the market")
        self.assertEqual(stream.push(""), [])
        self.assertEqual(stream.push("..."), [])
        self.assertEqual(stream.push("the market and bought"), ["and", "bought"])


class WordPacerTest(unittest.TestCase):
    def test_spreads_batch_over_expected_time(self):
        pacer = WordPacer()
        pacer.push(["a"] * 8, 0)
        self.assertEqual(pacer.next_interval(), 250)

    def test_interval_is_fixed_for_the_batch(self):
        pacer = WordPacer()
        pacer.push(["a"] * 8, 0)
        pacer.pop()
        pacer.pop()
        self.assertEqual(pacer.next_interval(), 250)

    def test_clamps_slow_interval(self):
        pacer = WordPacer()
        pacer.push(["a"], 0)
        self.assertEqual(pacer.next_interval(), MAX_INTERVAL_MS)

    def test_clamps_fast_interval(self):
        pacer = WordPacer()
        pacer.push(["a"] * 30, 0)
        self.assertEqual(pacer.interval_ms, MIN_INTERVAL_MS)

    def test_catches_up_on_large_backlog(self):
        pacer = WordPacer()
        pacer.push(["a"] * 4, 0)
        pacer.pending.extend(["b"] * CATCH_UP_BACKLOG)
        self.assertEqual(pacer.next_interval(), MIN_INTERVAL_MS)

    def test_spreads_over_measured_caption_period(self):
        pacer = WordPacer()
        pacer.push(["a"], 0)
        pacer.pop()
        # Captions keep arriving every 3 s; the period moves towards it.
        for i in range(1, 30):
            pacer.push([], i * 3_000)
        pacer.push(["a"] * 6, 30 * 3_000)
        self.assertAlmostEqual(pacer.next_interval(), 500, delta=5)

    def test_small_batch_fills_the_period(self):
        pacer = WordPacer()
        pacer.push(["a", "b", "c"], 0)
        self.assertEqual(pacer.next_interval(), 666)

    def test_measured_period_is_clamped(self):
        pacer = WordPacer()
        pacer.push([], 0)
        for i in range(1, 30):
            pacer.push([], i * 60_000)
        self.assertLessEqual(pacer.batch_ms, MAX_BATCH_MS)
        pacer.push(["a"] * 6, 31 * 60_000)
        self.assertLessEqual(pacer.next_interval(), MAX_INTERVAL_MS)

    def test_pops_in_order(self):
        pacer = WordPacer()
        pacer.push(["one", "two"], 0)
        self.assertEqual(pacer.pop(), "one")
        self.assertEqual(pacer.pop(), "two")
        self.assertIsNone(pacer.pop())
        self.assertEqual(len(pacer), 0)


if __name__ == "__main__":
    unittest.main()
