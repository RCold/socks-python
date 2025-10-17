# SPDX-License-Identifier: MIT
# Copyright (C) 2025 Yeuham Wang <rcold@rcold.name>

import asyncio
import logging
import socket
from asyncio import DatagramProtocol, DatagramTransport
from io import BytesIO
from socket import AddressFamily
from typing import Dict, Optional, Tuple

from error import ErrorKind, SocksError
from util import UDPSession

from .address import Address, AddrType

logger = logging.getLogger(__name__)


class UDPHeader:
    def __init__(self, addr: Optional[Address] = None) -> None:
        self.frag = 0
        self.dst = addr if addr is not None else Address()

    def parse(self, reader: BytesIO) -> None:
        _ = reader.read(2)
        self.frag = reader.read(1)[0]
        if self.frag != 0:
            raise SocksError(ErrorKind.FRAGMENTATION_NOT_SUPPORTED)
        self.dst.parse(reader)

    def pack(self) -> bytes:
        return bytes([0, 0, self.frag]) + self.dst.pack()


class UDPProtocol(DatagramProtocol):
    def __init__(self, session: UDPSession) -> None:
        self._session = session

    def datagram_received(self, data: bytes, addr: Tuple) -> None:
        if self._session.is_closing():
            return
        header = UDPHeader(Address(*addr[:2]))
        self._session.send(header.pack() + data)


async def handle_udp(session: UDPSession) -> None:
    loop = asyncio.get_event_loop()
    protocol = UDPProtocol(session)
    resolve_cache: Dict[str, Tuple[AddressFamily, str]] = {}
    transport_v4: Optional[DatagramTransport] = None
    transport_v6: Optional[DatagramTransport] = None
    try:
        transport_v4, _ = await loop.create_datagram_endpoint(
            lambda: protocol, ("0.0.0.0", 0)
        )
        transport_v6, _ = await loop.create_datagram_endpoint(
            lambda: protocol, ("::", 0)
        )
        while True:
            data = await session.recv()
            if data is None:
                break
            reader = BytesIO(data)
            header = UDPHeader()
            header.parse(reader)
            data = reader.read()
            if header.dst.type == AddrType.IP_V4:
                family = socket.AF_INET
                addr = (header.dst.addr, header.dst.port)
            elif header.dst.type == AddrType.DOMAIN_NAME:
                domain = header.dst.addr
                if domain in resolve_cache:
                    ip_info = resolve_cache[domain]
                else:
                    info_list = await loop.getaddrinfo(domain, 0)
                    if not info_list:
                        raise SocksError(ErrorKind.INVALID_DOMAIN_NAME)
                    ip_info = resolve_cache[domain] = (
                        info_list[0][0],
                        info_list[0][4][0],
                    )
                    logger.debug(f"domain name {domain} resolved to {ip_info[1]}")
                family = ip_info[0]
                addr = (ip_info[1], header.dst.port)
            elif header.dst.type == AddrType.IP_V6:
                family = socket.AF_INET6
                addr = (header.dst.addr, header.dst.port)
            else:
                raise SocksError(ErrorKind.INVALID_ADDRESS_TYPE)
            if family == socket.AF_INET:
                transport_v4.sendto(data, addr)
            elif family == socket.AF_INET6:
                transport_v6.sendto(data, addr)
    finally:
        if transport_v4 is not None:
            transport_v4.close()
        if transport_v6 is not None:
            transport_v6.close()
