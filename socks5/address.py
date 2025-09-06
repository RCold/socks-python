import socket
from asyncio import StreamReader, StreamWriter
from enum import IntEnum
from io import BytesIO
from ipaddress import IPv4Address, IPv6Address

from error import ErrorKind, SocksError


class AddrType(IntEnum):
    IP_V4 = 0x01
    DOMAIN_NAME = 0x03
    IP_V6 = 0x04


class Address:
    def __init__(self, addr: str = "0.0.0.0", port: int = 0) -> None:
        try:
            self.type = AddrType.IP_V4
            self.addr = str(IPv4Address(addr))
        except Exception:
            try:
                self.type = AddrType.IP_V6
                self.addr = str(IPv6Address(addr))
            except Exception:
                self.type = AddrType.DOMAIN_NAME
                self.addr = addr
        self.port = port

    async def read_from(self, reader: StreamReader) -> None:
        self.type = AddrType((await reader.readexactly(1))[0])
        if self.type == AddrType.IP_V4:
            self.addr = socket.inet_ntoa(await reader.readexactly(4))
        elif self.type == AddrType.DOMAIN_NAME:
            n = (await reader.readexactly(1))[0]
            if n < 1:
                raise SocksError(ErrorKind.INVALID_DOMAIN_NAME)
            data = await reader.readexactly(n)
            try:
                self.addr = data.decode()
            except Exception:
                raise SocksError(ErrorKind.INVALID_DOMAIN_NAME)
        elif self.type == AddrType.IP_V6:
            self.addr = socket.inet_ntop(socket.AF_INET6, await reader.readexactly(16))
        else:
            raise SocksError(ErrorKind.INVALID_ADDRESS_TYPE)
        self.port = int.from_bytes(await reader.readexactly(2))

    def write_to(self, writer: StreamWriter) -> None:
        writer.write(bytes([self.type]))
        if self.type == AddrType.IP_V4:
            writer.write(socket.inet_aton(self.addr))
        elif self.type == AddrType.DOMAIN_NAME:
            data = self.addr.encode()
            if not 1 <= len(data) <= 255:
                raise SocksError(ErrorKind.INVALID_DOMAIN_NAME)
            writer.write(bytes([len(data)]) + data)
        elif self.type == AddrType.IP_V6:
            writer.write(socket.inet_pton(socket.AF_INET6, self.addr))
        else:
            raise SocksError(ErrorKind.INVALID_ADDRESS_TYPE)
        writer.write(self.port.to_bytes(2))

    def parse(self, reader: BytesIO) -> None:
        self.type = AddrType(reader.read(1)[0])
        if self.type == AddrType.IP_V4:
            self.addr = socket.inet_ntoa(reader.read(4))
        elif self.type == AddrType.DOMAIN_NAME:
            n = reader.read(1)[0]
            if n < 1:
                raise SocksError(ErrorKind.INVALID_DOMAIN_NAME)
            data = reader.read(n)
            try:
                self.addr = data.decode()
            except Exception:
                raise SocksError(ErrorKind.INVALID_DOMAIN_NAME)
        elif self.type == AddrType.IP_V6:
            self.addr = socket.inet_ntop(socket.AF_INET6, reader.read(16))
        else:
            raise SocksError(ErrorKind.INVALID_ADDRESS_TYPE)
        self.port = int.from_bytes(reader.read(2))

    def pack(self) -> bytes:
        blocks = [bytes([self.type])]
        if self.type == AddrType.IP_V4:
            blocks.append(socket.inet_aton(self.addr))
        elif self.type == AddrType.DOMAIN_NAME:
            data = self.addr.encode()
            if not 1 <= len(data) <= 255:
                raise SocksError(ErrorKind.INVALID_DOMAIN_NAME)
            blocks.append(bytes([len(data)]) + data)
        elif self.type == AddrType.IP_V6:
            blocks.append(socket.inet_pton(socket.AF_INET6, self.addr))
        else:
            raise SocksError(ErrorKind.INVALID_ADDRESS_TYPE)
        blocks.append(self.port.to_bytes(2))
        return b"".join(blocks)
