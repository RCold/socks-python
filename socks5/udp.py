import asyncio
import socket
import struct
from asyncio import DatagramProtocol
from io import BytesIO
from ipaddress import IPv6Address
from typing import Dict, Tuple

from error import ErrorKind, SocksError
from util import UDPSession

from .address import Address, AddrType


class UDPHeader:
    def __init__(self, addr: Address = Address()) -> None:
        self.frag = 0
        self.addr = addr

    def parse(self, reader: BytesIO) -> None:
        try:
            _rsv, self.frag = struct.unpack("!HB", reader.read(3))
        except Exception:
            raise SocksError(ErrorKind.INVALID_UDP_PACKET_RECEIVED)
        if self.frag != 0:
            raise SocksError(ErrorKind.FRAGMENTATION_NOT_SUPPORTED)
        try:
            self.addr.parse(reader)
        except SocksError:
            raise
        except Exception:
            raise SocksError(ErrorKind.INVALID_UDP_PACKET_RECEIVED)

    def pack(self) -> bytes:
        return bytes([0, 0, self.frag]) + self.addr.pack()


class UDPProtocol(DatagramProtocol):
    def __init__(self, session: UDPSession) -> None:
        self._session = session

    def datagram_received(self, data: bytes, addr: Tuple) -> None:
        if self._session.is_closing():
            return
        try:
            address = Address(AddrType.IP_V6, str(IPv6Address(addr[0])), addr[1])
        except Exception:
            address = Address(AddrType.IP_V4, addr[0], addr[1])
        header = UDPHeader(address)
        self._session.send(header.pack() + data)


async def handle_udp(session: UDPSession) -> None:
    loop = asyncio.get_event_loop()
    protocol = UDPProtocol(session)
    try:
        transport_v4, _ = await loop.create_datagram_endpoint(
            lambda: protocol, ("0.0.0.0", 0)
        )
        transport_v6, _ = await loop.create_datagram_endpoint(
            lambda: protocol, ("::", 0)
        )
        resolve_cache: Dict[Tuple[str, int], Tuple] = {}
        while True:
            data = await session.recv()
            if data is None:
                break
            reader = BytesIO(data)
            header = UDPHeader()
            header.parse(reader)
            data = reader.read()
            key = (header.addr.addr, header.addr.port)
            if key in resolve_cache:
                addr_info = resolve_cache[key]
            else:
                addr_info_list = await loop.getaddrinfo(
                    header.addr.addr, header.addr.port
                )
                if not addr_info_list:
                    raise SocksError(ErrorKind.INVALID_DOMAIN_NAME)
                addr_info = resolve_cache[key] = addr_info_list[0]
            if addr_info[0] == socket.AF_INET:
                transport_v4.sendto(data, addr_info[4])
            elif addr_info[0] == socket.AF_INET6:
                transport_v6.sendto(data, addr_info[4])
    finally:
        transport_v4.close()
        transport_v6.close()
