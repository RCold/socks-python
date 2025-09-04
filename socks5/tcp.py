import asyncio
import logging
import socket
from asyncio import StreamReader, StreamWriter
from enum import IntEnum
from ipaddress import IPv6Address
from typing import Optional, Tuple

import util
from error import ErrorKind, SocksError
from util import UDPSession

from . import auth, udp
from .address import Address, AddrType

logger = logging.getLogger(__name__)


class Command(IntEnum):
    CONNECT = 0x01
    BIND = 0x02
    UDP_ASSOCIATE = 0x03


class ReplyCode(IntEnum):
    SUCCEEDED = 0x00
    GENERAL_SOCKS_SERVER_FAILURE = 0x01
    CONNECTION_NOT_ALLOWED_BY_RULESET = 0x02
    NETWORK_UNREACHABLE = 0x03
    HOST_UNREACHABLE = 0x04
    CONNECTION_REFUSED = 0x05
    TTL_EXPIRED = 0x06
    COMMAND_NOT_SUPPORTED = 0x07
    ADDRESS_TYPE_NOT_SUPPORTED = 0x08


class Reply:
    def __init__(self, rep: ReplyCode, bind: Optional[Address] = None) -> None:
        self.rep = rep
        self.bind = bind if bind is not None else Address()

    async def write_to(self, writer: StreamWriter) -> None:
        writer.write(bytes([5, self.rep, 0]))
        self.bind.write_to(writer)
        await writer.drain()


class Request:
    def __init__(self) -> None:
        self.cmd: Optional[Command] = None
        self.addr = Address()

    async def read_from(self, reader: StreamReader, writer: StreamWriter) -> None:
        ver = (await reader.readexactly(1))[0]
        if ver != 5:
            raise SocksError(ErrorKind.VERSION_MISMATCH)
        self.cmd = Command((await reader.readexactly(1))[0])
        if self.cmd not in [Command.CONNECT, Command.BIND, Command.UDP_ASSOCIATE]:
            await Reply(ReplyCode.COMMAND_NOT_SUPPORTED).write_to(writer)
            raise SocksError(ErrorKind.INVALID_COMMAND)
        _rsv = await reader.readexactly(1)
        try:
            await self.addr.read_from(reader)
        except SocksError as err:
            if err.kind == ErrorKind.INVALID_ADDRESS_TYPE:
                await Reply(ReplyCode.ADDRESS_TYPE_NOT_SUPPORTED).write_to(writer)
            raise


async def handle_connect(
    reader: StreamReader, writer: StreamWriter, addr: str, port: int
) -> None:
    try:
        remote_reader, remote_writer = await asyncio.open_connection(addr, port)
    except Exception:
        try:
            await Reply(ReplyCode.GENERAL_SOCKS_SERVER_FAILURE).write_to(writer)
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
        await Reply(ReplyCode.SUCCEEDED).write_to(writer)
        await util.copy_bidirectional(reader, writer, remote_reader, remote_writer)
        logger.debug(f"tcp://{remote_addr} disconnected")
    finally:
        await util.close_writer(remote_writer)


async def handle_udp_associate(
    reader: StreamReader, writer: StreamWriter, client_ip: str
) -> None:
    async def client_connected_cb(session: UDPSession, addr: Tuple) -> None:
        client_addr = util.format_addr(*addr[:2])
        if addr[0] != client_ip:
            logger.info(
                f"udp packets from client {client_addr} dropped: client ip address not allowed"
            )
            return
        logger.debug(f"udp session for client {client_addr} opened")
        try:
            await udp.handle_udp(session)
        except Exception as err:
            logger.error(
                f"failed to handle udp packet from client {client_addr}: {err}"
            )
        logger.debug(f"udp session for client {client_addr} closed")

    try:
        bind_addr = writer.get_extra_info("sockname")[0]
        server = await util.start_udp_server(client_connected_cb, (bind_addr, 0))
    except Exception:
        try:
            await Reply(ReplyCode.GENERAL_SOCKS_SERVER_FAILURE).write_to(writer)
        except Exception:
            pass
        raise
    try:
        bind_addr, bind_port = server.sockets[0].getsockname()[:2]
        try:
            addr = Address(AddrType.IP_V6, str(IPv6Address(bind_addr)), bind_port)
        except Exception:
            addr = Address(AddrType.IP_V4, bind_addr, bind_port)
        await Reply(ReplyCode.SUCCEEDED, addr).write_to(writer)
        while await reader.read(16 * 1024):
            pass
    finally:
        server.close()
        await server.wait_closed()


async def handle_tcp(reader: StreamReader, writer: StreamWriter) -> None:
    peername = writer.get_extra_info("peername")[:2]
    client_addr = util.format_addr(*peername)
    if not await auth.authenticate(reader, writer):
        logger.info(
            f"socks5 request from {client_addr} rejected: authentication failed"
        )
        return
    request = Request()
    await request.read_from(reader, writer)
    remote_addr = util.format_addr(request.addr.addr, request.addr.port)
    if request.cmd == Command.CONNECT:
        logger.info(
            f"socks5 connect request from client {client_addr} to tcp://{remote_addr} accepted"
        )
        await handle_connect(reader, writer, request.addr.addr, request.addr.port)
    elif request.cmd == Command.BIND:
        logger.info(
            f"socks5 bind request from client {client_addr} rejected: not implemented"
        )
        await Reply(ReplyCode.COMMAND_NOT_SUPPORTED).write_to(writer)
    elif request.cmd == Command.UDP_ASSOCIATE:
        logger.info(
            f"socks5 udp associate request from client {client_addr} to udp://{remote_addr} accepted"
        )
        await handle_udp_associate(reader, writer, peername[0])
