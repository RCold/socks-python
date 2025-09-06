from asyncio import StreamReader, StreamWriter
from enum import IntEnum


class Method(IntEnum):
    NO_AUTHENTICATION_REQUIRED = 0x00
    GSSAPI = 0x01
    USERNAME_PASSWORD = 0x02
    NO_ACCEPTABLE_AUTH_METHODS = 0xFF


async def send_response(writer: StreamWriter, method: Method) -> None:
    writer.write(bytes([5, method]))
    await writer.drain()


async def authenticate(reader: StreamReader, writer: StreamWriter) -> bool:
    n = (await reader.readexactly(1))[0]
    methods = await reader.readexactly(n)
    if Method.NO_AUTHENTICATION_REQUIRED in methods:
        await send_response(writer, Method.NO_AUTHENTICATION_REQUIRED)
        return True
    else:
        await send_response(writer, Method.NO_ACCEPTABLE_AUTH_METHODS)
        return False
