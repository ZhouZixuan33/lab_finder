"""Rate-limited HTTP requests with bounded retry behavior."""

import datetime as datetime_module
from email.utils import parsedate_to_datetime

import httpx

from lab_tracker.services.rate_limit import SerialRateLimiter

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=datetime_module.UTC)
        now = datetime_module.datetime.now(datetime_module.UTC)
        return max(0.0, (retry_at - now).total_seconds())


class RateLimitedHttpClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        limiter: SerialRateLimiter,
        *,
        max_retries: int = 3,
        backoff_base_seconds: float = 1.0,
        max_backoff_seconds: float = 8.0,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.client = client
        self.limiter = limiter
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.max_backoff_seconds = max_backoff_seconds

    async def get(self, url: str, **kwargs: object) -> httpx.Response:
        retry_delay = 0.0
        for attempt in range(self.max_retries + 1):
            async with self.limiter.slot(delay_seconds=retry_delay):
                response = await self.client.get(url, **kwargs)

            should_retry = response.status_code in RETRYABLE_STATUS_CODES
            if not should_retry or attempt == self.max_retries:
                response.raise_for_status()
                return response

            header_delay = parse_retry_after(response.headers.get("Retry-After"))
            exponential_delay = min(
                self.max_backoff_seconds,
                self.backoff_base_seconds * (2**attempt),
            )
            retry_delay = header_delay if header_delay is not None else exponential_delay

        raise RuntimeError("Unreachable HTTP retry state")  # pragma: no cover

    async def get_text(self, url: str, **kwargs: object) -> str:
        return (await self.get(url, **kwargs)).text
