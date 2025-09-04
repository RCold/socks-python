from asyncio import StreamReader, StreamWriter
from enum import IntEnum


class Method(IntEnum):
    NO_AUTHENTICATION_REQUIRED = 0x00
    GSSAPI = 0x01
    USERNAME_PASSWORD = 0x02
    NO_ACCEPTABLE_AUTH_METHODS = 0xFF


class Reply:
    def __init__(self, method: Method) -> None:
        self.method = method

    async def write(self, writer: StreamWriter) -> None:
        writer.write(bytes([5, self.method]))
        await writer.drain()


async def authenticate(reader: StreamReader, writer: StreamWriter) -> bool:
    n = (await reader.readexactly(1))[0]
    methods = await reader.readexactly(n)
    if Method.NO_AUTHENTICATION_REQUIRED in methods:
        await Reply(Method.NO_AUTHENTICATION_REQUIRED).write(writer)
        return True
    else:
        await Reply(Method.NO_ACCEPTABLE_AUTH_METHODS).write(writer)
        return False
