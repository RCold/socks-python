import enum
from enum import Enum


class ErrorKind(Enum):
    VERSION_MISMATCH = enum.auto()
    INVALID_AUTH_METHOD = enum.auto()
    INVALID_ADDRESS_TYPE = enum.auto()
    INVALID_COMMAND = enum.auto()
    INVALID_DOMAIN_NAME = enum.auto()
    FRAGMENTATION_NOT_SUPPORTED = enum.auto()


class SocksError(Exception):
    def __init__(self, kind: ErrorKind) -> None:
        self.kind = kind
        messages = {
            ErrorKind.VERSION_MISMATCH: "version mismatch",
            ErrorKind.INVALID_AUTH_METHOD: "invalid auth method",
            ErrorKind.INVALID_ADDRESS_TYPE: "invalid address type",
            ErrorKind.INVALID_COMMAND: "invalid command",
            ErrorKind.INVALID_DOMAIN_NAME: "invalid domain name",
            ErrorKind.FRAGMENTATION_NOT_SUPPORTED: "fragmentation not supported",
        }
        super().__init__(messages.get(kind, "unknown error"))
