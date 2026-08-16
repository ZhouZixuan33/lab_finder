import httpx
import pytest

from lab_tracker.services.http import RateLimitedHttpClient
from lab_tracker.services.rate_limit import SerialRateLimiter


class FakeTime:
    def __init__(self) -> None:
        self.current = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.current

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.current += delay


@pytest.mark.asyncio
async def test_limiter_serializes_starts_at_least_one_second_apart() -> None:
    time = FakeTime()
    limiter = SerialRateLimiter(
        min_interval_seconds=1.0,
        clock=time.monotonic,
        sleep=time.sleep,
    )
    starts: list[float] = []

    async with limiter.slot():
        starts.append(time.monotonic())
    async with limiter.slot():
        starts.append(time.monotonic())

    assert starts == [0.0, 1.0]
    assert time.sleeps == [1.0]


@pytest.mark.asyncio
async def test_http_client_honors_retry_after_and_then_succeeds() -> None:
    time = FakeTime()
    limiter = SerialRateLimiter(1.0, clock=time.monotonic, sleep=time.sleep)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "3"}, request=request)
        return httpx.Response(200, text="ok", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await RateLimitedHttpClient(
            client,
            limiter,
            max_retries=2,
        ).get("https://example.edu/data")

    assert response.text == "ok"
    assert calls == 2
    assert time.sleeps == [3.0]


@pytest.mark.asyncio
async def test_http_client_uses_finite_exponential_backoff() -> None:
    time = FakeTime()
    limiter = SerialRateLimiter(1.0, clock=time.monotonic, sleep=time.sleep)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        requester = RateLimitedHttpClient(client, limiter, max_retries=2)
        with pytest.raises(httpx.HTTPStatusError):
            await requester.get("https://example.edu/data")

    assert calls == 3
    assert time.sleeps == [1.0, 2.0]
