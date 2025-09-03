import asyncio
import logging
import os
import time
from asyncio import (
    AbstractEventLoop,
    BaseTransport,
    CancelledError,
    DatagramProtocol,
    DatagramTransport,
    Future,
    Queue,
    QueueFull,
    StreamReader,
    StreamWriter,
)
from ipaddress import IPv6Address
from logging import LogRecord
from typing import Awaitable, Callable, Dict, Optional, Tuple


async def close_writer(writer: StreamWriter) -> None:
    if writer.is_closing():
        return
    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass


async def copy(reader: StreamReader, writer: StreamWriter) -> None:
    while True:
        data = await reader.read(16 * 1024)
        if not data or writer.is_closing():
            break
        writer.write(data)
        await writer.drain()
    await close_writer(writer)


async def copy_bidirectional(
    reader1: StreamReader,
    writer1: StreamWriter,
    reader2: StreamReader,
    writer2: StreamWriter,
) -> None:
    await asyncio.gather(
        copy(reader1, writer2),
        copy(reader2, writer1),
    )


def format_addr(addr: str, port: int) -> str:
    try:
        return f"[{IPv6Address(addr)}]:{port}"
    except Exception:
        return f"{addr}:{port}"


class UDPSession:
    def __init__(self, transport: DatagramTransport, addr: Tuple) -> None:
        self._transport = transport
        self._addr = addr
        self._queue: Queue[Optional[bytes]] = Queue(128)

    def send(self, data: bytes) -> None:
        if self._transport.is_closing():
            raise RuntimeError("server connection is closed")
        self._transport.sendto(data, self._addr)

    async def recv(self) -> Optional[bytes]:
        return await self._queue.get()

    def is_closing(self) -> bool:
        return self._transport.is_closing()

    def feed_data(self, data: Optional[bytes]) -> None:
        try:
            self._queue.put_nowait(data)
        except QueueFull:
            pass


class UDPSessionProtocol(DatagramProtocol):
    def __init__(
        self,
        loop: AbstractEventLoop,
        client_connected_cb: Callable[[UDPSession, Tuple], Awaitable[None]],
    ) -> None:
        self._loop = loop
        self._client_connected_cb = client_connected_cb
        self._transport: Optional[DatagramTransport] = None
        self._sessions: Dict[Tuple, UDPSession] = {}
        self._connection_lost_fut = loop.create_future()

    def connection_made(self, transport: BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]

    def connection_lost(self, exc: Optional[Exception]) -> None:
        for session in self._sessions.values():
            session.feed_data(None)
        if exc is not None:
            self._connection_lost_fut.set_exception(exc)
        else:
            self._connection_lost_fut.set_result(None)

    def datagram_received(self, data: bytes, addr: Tuple) -> None:
        self._loop.create_task(self._handle_datagram(data, addr))

    def close_waiter(self) -> Awaitable[None]:
        return self._connection_lost_fut

    async def _handle_datagram(self, data: bytes, addr: Tuple) -> None:
        if addr in self._sessions:
            session = self._sessions[addr]
            session.feed_data(data)
        elif self._transport is not None:
            session = self._sessions[addr] = UDPSession(self._transport, addr)
            session.feed_data(data)
            await self._client_connected_cb(session, addr)


class UDPServer:
    def __init__(
        self,
        loop: AbstractEventLoop,
        transport: DatagramTransport,
        protocol: UDPSessionProtocol,
    ) -> None:
        self._loop = loop
        self._transport = transport
        self._protocol = protocol
        self._closed = False
        self._serving_forever_fut: Optional[Future] = None

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._transport.close()
        if (
            self._serving_forever_fut is not None
            and not self._serving_forever_fut.done()
        ):
            self._serving_forever_fut.cancel()
            self._serving_forever_fut = None

    async def wait_closed(self) -> None:
        if not self._closed:
            await self._protocol.close_waiter()

    def is_serving(self) -> bool:
        return not self._closed

    @property
    def sockets(self) -> list:
        if self._closed:
            return []
        sock = self._transport.get_extra_info("socket")
        return [sock] if sock else []

    async def serve_forever(self) -> None:
        if self._serving_forever_fut is not None:
            raise RuntimeError(
                f"server {self!r} is already being awaited on serve_forever()"
            )
        self._serving_forever_fut = self._loop.create_future()
        try:
            await self._serving_forever_fut
        except CancelledError:
            try:
                self.close()
                await self.wait_closed()
            finally:
                raise
        finally:
            self._serving_forever_fut = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.close()
        await self.wait_closed()


async def start_udp_server(
    client_connected_cb: Callable[[UDPSession, Tuple], Awaitable[None]],
    local_addr: Optional[Tuple] = None,
    remote_addr: Optional[Tuple] = None,
    **kwargs,
) -> UDPServer:
    loop = asyncio.get_running_loop()
    protocol = UDPSessionProtocol(loop, client_connected_cb)
    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol, local_addr, remote_addr, **kwargs
    )
    server = UDPServer(loop, transport, protocol)
    return server


class Formatter(logging.Formatter):
    converter = time.gmtime

    def format(self, record: LogRecord) -> str:
        timestamp = self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ")
        formatted = (
            f"[{timestamp} {record.levelname:5} {record.name}] {record.getMessage()}"
        )
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            if formatted[-1:] != "\n":
                formatted += "\n"
            formatted += record.exc_text
        return formatted


def init_logging() -> None:
    log_level_str = os.environ.get("PYTHON_LOG", "WARNING").upper()
    log_levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
        "FATAL": logging.CRITICAL,
    }
    log_level = log_levels.get(log_level_str, logging.WARNING)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(Formatter())
    logging.basicConfig(level=log_level, handlers=[console_handler])
