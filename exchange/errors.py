LIVE_DISABLED_MESSAGE = "LIVE ORDER EXECUTION DISABLED: paper mode only."


class LiveOrderExecutionDisabled(RuntimeError):
    """Raised on any attempt to place, edit, cancel, preview or otherwise act on a real order,
    or to move funds. There is no code path in this project that performs these actions."""

    def __init__(self, detail: str = ""):
        super().__init__(LIVE_DISABLED_MESSAGE + (f" ({detail})" if detail else ""))


class ForbiddenEndpointError(LiveOrderExecutionDisabled):
    """Raised by the transport for any request outside the read-only allowlist."""


class ExchangeAPIError(RuntimeError):
    """A read-only request failed (HTTP error, bad payload, network). Messages never include
    response bodies or request headers, so they cannot echo credentials or tokens."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status
