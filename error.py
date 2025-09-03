import enum
from enum import Enum


class ErrorKind(Enum):
    VERSION_MISMATCH = enum.auto()
    NO_ACCEPTABLE_AUTH_METHODS = enum.auto()
    ADDRESS_TYPE_NOT_SUPPORTED = enum.auto()
    COMMAND_NOT_SUPPORTED = enum.auto()
    INVALID_DOMAIN_NAME = enum.auto()
    FRAGMENTATION_NOT_SUPPORTED = enum.auto()
    INVALID_UDP_PACKET_RECEIVED = enum.auto()


class SocksError(Exception):
    def __init__(self, kind: ErrorKind) -> None:
        self.kind = kind
        messages = {
            ErrorKind.VERSION_MISMATCH: "version mismatch",
            ErrorKind.NO_ACCEPTABLE_AUTH_METHODS: "no acceptable authentication methods",
            ErrorKind.ADDRESS_TYPE_NOT_SUPPORTED: "address type not supported",
            ErrorKind.COMMAND_NOT_SUPPORTED: "command not supported",
            ErrorKind.INVALID_DOMAIN_NAME: "invalid domain name",
            ErrorKind.FRAGMENTATION_NOT_SUPPORTED: "fragmentation not supported",
            ErrorKind.INVALID_UDP_PACKET_RECEIVED: "invalid udp packet received",
        }
        super().__init__(messages.get(kind, "unknown error"))
