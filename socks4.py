import asyncio
import logging
import socket
from asyncio import StreamReader, StreamWriter
from enum import IntEnum

import util
from error import ErrorKind, SocksError

logger = logging.getLogger(__name__)


class Command(IntEnum):
    CONNECT = 1
    BIND = 2


class ReplyCode(IntEnum):
    REQUEST_GRANTED = 90
    REQUEST_REJECTED_OR_FAILED = 91


async def send_response(writer: StreamWriter, rep: ReplyCode) -> None:
    writer.write(bytes((0, rep, 0, 0, 0, 0, 0, 0)))
    await writer.drain()


async def handle_connect(
    reader: StreamReader, writer: StreamWriter, addr: str, port: int
) -> None:
    try:
        remote_reader, remote_writer = await asyncio.open_connection(addr, port)
    except Exception:
        try:
            await send_response(writer, ReplyCode.REQUEST_REJECTED_OR_FAILED)
        except Exception:
            pass
        raise
    try:
        sock = remote_writer.get_extra_info("socket")
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    try:
        remote_addr = util.format_addr(addr, port)
        logger.debug(f"tcp://{remote_addr} connected")
        await send_response(writer, ReplyCode.REQUEST_GRANTED)
        await util.copy_bidirectional(reader, writer, remote_reader, remote_writer)
        logger.debug(f"tcp://{remote_addr} disconnected")
    finally:
        await util.close_writer(remote_writer)


async def handle_tcp(reader: StreamReader, writer: StreamWriter) -> None:
    cmd = (await reader.readexactly(1))[0]
    if cmd not in [Command.CONNECT, Command.BIND]:
        try:
            await send_response(writer, ReplyCode.REQUEST_REJECTED_OR_FAILED)
        except Exception:
            pass
        raise SocksError(ErrorKind.INVALID_COMMAND)
    port = int.from_bytes(await reader.readexactly(2))
    data = await reader.readexactly(4)
    _user_id = await reader.readuntil(b"\0")
    if data[:3] == bytes([0, 0, 0]) and data[3] != 0:
        data = (await reader.readuntil(b"\0"))[:-1]
        try:
            addr = data.decode()
        except Exception:
            raise SocksError(ErrorKind.INVALID_DOMAIN_NAME)
        if not 1 <= len(addr) <= 255:
            raise SocksError(ErrorKind.INVALID_DOMAIN_NAME)
    else:
        addr = socket.inet_ntoa(data)
    client_addr = util.format_addr(*writer.get_extra_info("peername")[:2])
    remote_addr = util.format_addr(addr, port)
    if cmd == Command.CONNECT:
        logger.info(
            f"socks4 connect request from client {client_addr} to tcp://{remote_addr} accepted"
        )
        await handle_connect(reader, writer, addr, port)
    elif cmd == Command.BIND:
        logger.info(
            f"socks4 bind request from client {client_addr} rejected: not implemented"
        )
        await send_response(writer, ReplyCode.REQUEST_REJECTED_OR_FAILED)
