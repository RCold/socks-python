import asyncio
import socket
from asyncio import DatagramProtocol
from io import BytesIO
from typing import Dict, Optional, Tuple

from error import ErrorKind, SocksError
from util import UDPSession

from .address import Address


class UDPHeader:
    def __init__(self, addr: Optional[Address] = None) -> None:
        self.frag = 0
        self.addr = addr if addr is not None else Address()

    def parse(self, reader: BytesIO) -> None:
        _rsv = reader.read(2)
        self.frag = reader.read(1)[0]
        if self.frag != 0:
            raise SocksError(ErrorKind.FRAGMENTATION_NOT_SUPPORTED)
        self.addr.parse(reader)

    def pack(self) -> bytes:
        return bytes([0, 0, self.frag]) + self.addr.pack()


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
    resolve_cache: Dict[Tuple[str, int], Tuple] = {}
    transport_v4 = None
    transport_v6 = None
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
            sock_addr = (header.addr.addr, header.addr.port)
            if sock_addr in resolve_cache:
                addr_info = resolve_cache[sock_addr]
            else:
                addr_info_list = await loop.getaddrinfo(*sock_addr)
                if not addr_info_list:
                    raise SocksError(ErrorKind.INVALID_DOMAIN_NAME)
                addr_info = resolve_cache[sock_addr] = addr_info_list[0]
            if addr_info[0] == socket.AF_INET:
                transport_v4.sendto(data, addr_info[4])
            elif addr_info[0] == socket.AF_INET6:
                transport_v6.sendto(data, addr_info[4])
    finally:
        if transport_v4 is not None:
            transport_v4.close()
        if transport_v6 is not None:
            transport_v6.close()
