from __future__ import annotations

from .device import CH9329FDevice


class UARTConnection(CH9329FDevice):
    """CH9329F connection through its UART protocol interface."""

    @classmethod
    def open(
        cls,
        port: str,
        baudrate: int = 9600,
        *,
        address: int = 0,
        timeout: float = 0.5,
        trace=None,
    ) -> "UARTConnection":
        return cls.open_serial(
            port,
            baudrate,
            address=address,
            timeout=timeout,
            trace=trace,
        )


class CH9329F:
    """Factory for the UART protocol connection."""

    @staticmethod
    def uart(
        port: str,
        baudrate: int = 9600,
        *,
        address: int = 0,
        timeout: float = 0.5,
        trace=None,
    ) -> UARTConnection:
        return UARTConnection.open(
            port,
            baudrate,
            address=address,
            timeout=timeout,
            trace=trace,
        )
