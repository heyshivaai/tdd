"""
Rate limiter for Anthropic Claude API calls.

Why: The Anthropic API enforces token-per-minute (TPM) rate limits.
At Tier 2 this is 450K input TPM. When running a full VDR scan with
25+ batches, we can exceed this if we don't pace our calls. This
module tracks cumulative token usage and pauses when approaching
the limit.
"""
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token-bucket rate limiter for Claude API calls.

    Tracks token usage within a sliding window and pauses execution
    when the next call would exceed the rate limit.
    """

    def __init__(
        self,
        max_tokens_per_minute: int = 400_000,
        window_seconds: float = 60.0,
    ):
        """
        Args:
            max_tokens_per_minute: Maximum tokens allowed per window.
                Default 400K (conservative buffer under Tier 2's 450K limit).
            window_seconds: Sliding window duration in seconds.
        """
        self.max_tokens = max_tokens_per_minute
        self.window = window_seconds
        self._usage: list[tuple[float, int]] = []  # (timestamp, tokens)
        self._total_tokens = 0
        self._total_calls = 0
        self._total_wait_seconds = 0.0

    def _prune_old(self) -> None:
        """Remove usage records older than the sliding window."""
        cutoff = time.time() - self.window
        while self._usage and self._usage[0][0] < cutoff:
            self._usage.pop(0)

    def _current_usage(self) -> int:
        """Sum of tokens used in the current window."""
        self._prune_old()
        return sum(tokens for _, tokens in self._usage)

    def wait_if_needed(self, next_estimated_tokens: int = 0) -> float:
        """
        Pause if the next call would exceed the rate limit.

        Args:
            next_estimated_tokens: Estimated tokens for the upcoming call.

        Returns:
            Number of seconds waited (0.0 if no wait was needed).
        """
        self._prune_old()
        current = self._current_usage()

        if current + next_estimated_tokens <= self.max_tokens:
            return 0.0

        # Calculate how long to wait for enough budget to free up
        # Find the oldest record that, if expired, would free enough tokens
        needed = (current + next_estimated_tokens) - self.max_tokens
        freed = 0
        wait_until = time.time()

        for ts, tokens in self._usage:
            freed += tokens
            wait_until = ts + self.window
            if freed >= needed:
                break

        wait_seconds = max(0.0, wait_until - time.time() + 0.5)  # +0.5s buffer
        if wait_seconds > 0:
            logger.info(
                "Rate limiter: pausing %.1fs (current window: %d tokens, next call: ~%d tokens)",
                wait_seconds, current, next_estimated_tokens,
            )
            time.sleep(wait_seconds)
            self._total_wait_seconds += wait_seconds

        return wait_seconds

    def record_usage(self, tokens_used: int) -> None:
        """
        Record token usage from a completed API call.

        Args:
            tokens_used: Number of tokens consumed (input + output).
        """
        self._usage.append((time.time(), tokens_used))
        self._total_tokens += tokens_used
        self._total_calls += 1

    def stats(self) -> dict:
        """Return cumulative rate limiter statistics."""
        return {
            "total_tokens": self._total_tokens,
            "total_calls": self._total_calls,
            "total_wait_seconds": round(self._total_wait_seconds, 1),
            "current_window_tokens": self._current_usage(),
        }
