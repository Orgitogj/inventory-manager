from concurrent.futures import ThreadPoolExecutor

from app.auth.rate_limit import LoginRateLimiter

IP = "203.0.113.7"
EMAIL = "ana@shop.al"
WINDOW = 900


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def build(clock: FakeClock, max_attempts: int = 3, max_attempts_per_ip: int = 5):
    return LoginRateLimiter(
        max_attempts=max_attempts,
        max_attempts_per_ip=max_attempts_per_ip,
        window_seconds=WINDOW,
        clock=clock,
    )


def test_allows_attempts_below_the_limit():
    limiter = build(FakeClock())

    limiter.record_failure(IP, EMAIL)
    limiter.record_failure(IP, EMAIL)

    assert limiter.retry_after(IP, EMAIL) is None


def test_blocks_at_the_limit_and_reports_the_remaining_seconds():
    clock = FakeClock()
    limiter = build(clock)

    for _ in range(3):
        limiter.record_failure(IP, EMAIL)
        clock.advance(10)

    assert limiter.retry_after(IP, EMAIL) == WINDOW - 30


def test_window_slides_one_failure_at_a_time():
    clock = FakeClock()
    limiter = build(clock)

    for _ in range(3):
        limiter.record_failure(IP, EMAIL)
        clock.advance(100)

    clock.advance(WINDOW - 300)
    assert limiter.retry_after(IP, EMAIL) is None

    limiter.record_failure(IP, EMAIL)
    assert limiter.retry_after(IP, EMAIL) == 100


def test_other_email_and_other_ip_are_counted_separately():
    limiter = build(FakeClock())

    for _ in range(3):
        limiter.record_failure(IP, EMAIL)

    assert limiter.retry_after(IP, EMAIL) is not None
    assert limiter.retry_after(IP, "vera@shop.al") is None
    assert limiter.retry_after("198.51.100.9", EMAIL) is None


def test_ip_limit_counts_failures_across_emails():
    limiter = build(FakeClock())

    for number in range(5):
        limiter.record_failure(IP, f"user{number}@shop.al")

    assert limiter.retry_after(IP, "fresh@shop.al") == WINDOW
    assert limiter.retry_after("198.51.100.9", "fresh@shop.al") is None


def test_reset_clears_the_pair_but_not_the_ip_counter():
    limiter = build(FakeClock())

    for _ in range(3):
        limiter.record_failure(IP, EMAIL)

    limiter.reset(IP, EMAIL)
    assert limiter.retry_after(IP, EMAIL) is None

    limiter.record_failure(IP, "vera@shop.al")
    limiter.record_failure(IP, "vera@shop.al")
    assert limiter.retry_after(IP, EMAIL) == WINDOW


def test_expired_failures_are_forgotten():
    clock = FakeClock()
    limiter = build(clock)

    for number in range(5):
        limiter.record_failure(f"198.51.100.{number}", EMAIL)

    clock.advance(WINDOW)
    limiter.record_failure(IP, EMAIL)

    assert set(limiter._failures) == {(IP, EMAIL), IP}


def test_concurrent_failures_are_all_counted():
    limiter = build(FakeClock(), max_attempts=1000, max_attempts_per_ip=1000)

    with ThreadPoolExecutor(max_workers=8) as executor:
        for _ in range(999):
            executor.submit(limiter.record_failure, IP, EMAIL)

    assert limiter.retry_after(IP, EMAIL) is None

    limiter.record_failure(IP, EMAIL)
    assert limiter.retry_after(IP, EMAIL) == WINDOW
