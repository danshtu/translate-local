from collections import deque

# Overlap trimming between consecutive captions
MAX_OVERLAP_WORDS = 8
MIN_SINGLE_WORD_OVERLAP = 4
STRIP_CHARS = ".,!?;:\"'()[]«»“”‘’…-–—"

# Word pacing. A new caption arrives roughly every chunk step
# (CHUNK_DURATION - OVERLAP_DURATION in live_translator.py); the real period
# is measured as an average of the gaps between captions.
EXPECTED_BATCH_MS = 2_000
MIN_BATCH_MS = 1_000
MAX_BATCH_MS = 5_000
BATCH_SMOOTHING = 0.3
MIN_INTERVAL_MS = 90
MAX_INTERVAL_MS = 900
CATCH_UP_BACKLOG = 20


def normalize_word(word):
    return word.casefold().strip(STRIP_CHARS)


def _content_words(words):
    """Return (index, normalized) for words that are not just punctuation."""
    return [(i, n) for i, w in enumerate(words) if (n := normalize_word(w))]


def new_words(previous_words, caption):
    """Return the words of caption that do not repeat the end of previous_words."""
    words = caption.split()
    previous = [n for _, n in _content_words(previous_words)]
    current = _content_words(words)

    start = 0
    longest = min(MAX_OVERLAP_WORDS, len(previous), len(current))
    for k in range(longest, 0, -1):
        if previous[-k:] != [n for _, n in current[:k]]:
            continue
        # A single shared short word ("the", "a") is usually a coincidence.
        if k == 1 and len(current[0][1]) < MIN_SINGLE_WORD_OVERLAP:
            continue
        start = current[k - 1][0] + 1
        break

    result = words[start:]
    while result and not normalize_word(result[0]):
        result.pop(0)
    return result


class CaptionStream:
    """Turn overlapping captions into a stream of only the new words."""

    def __init__(self):
        self.previous_words = []

    def push(self, caption):
        # Empty or punctuation-only captions say nothing about the overlap.
        if not _content_words(caption.split()):
            return []
        words = new_words(self.previous_words, caption)
        self.previous_words = caption.split()
        return words


class WordPacer:
    """Queue words and spread them evenly until the next caption arrives."""

    def __init__(self):
        self.pending = deque()
        self.batch_ms = EXPECTED_BATCH_MS
        self.last_arrival_ms = None
        self.interval_ms = MAX_INTERVAL_MS

    def __len__(self):
        return len(self.pending)

    def push(self, words, now_ms):
        """Add a caption's new words; now_ms is a monotonic time in ms."""
        if self.last_arrival_ms is not None:
            gap = max(MIN_BATCH_MS, min(MAX_BATCH_MS, now_ms - self.last_arrival_ms))
            self.batch_ms += BATCH_SMOOTHING * (gap - self.batch_ms)
        self.last_arrival_ms = now_ms

        self.pending.extend(words)
        if self.pending:
            self.interval_ms = int(
                max(
                    MIN_INTERVAL_MS,
                    min(MAX_INTERVAL_MS, self.batch_ms / len(self.pending)),
                )
            )

    def pop(self):
        return self.pending.popleft() if self.pending else None

    def next_interval(self):
        # Far behind the speaker: reveal as fast as allowed to catch up.
        if len(self.pending) > CATCH_UP_BACKLOG:
            return MIN_INTERVAL_MS
        return self.interval_ms
