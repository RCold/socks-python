import asyncio
import logging
import socket
import sys
from asyncio import StreamReader, StreamWriter

import socks4
import socks5
import util
from error import ErrorKind, SocksError

logger = logging.getLogger(__name__)


async def client_connected_cb(reader: StreamReader, writer: StreamWriter) -> None:
    client_addr = util.format_addr(*writer.get_extra_info("peername")[:2])
    logger.debug(f"client {client_addr} connected")
    try:
        sock = writer.get_extra_info("socket")
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    try:
        ver = (await reader.readexactly(1))[0]
        if ver == 4:
            logger.debug(f"handle socks4 request from client {client_addr}")
            await socks4.handle_tcp(reader, writer)
        elif ver == 5:
            logger.debug(f"handle socks5 request from client {client_addr}")
            await socks5.handle_tcp(reader, writer)
        else:
            raise SocksError(ErrorKind.VERSION_MISMATCH)
    except Exception as err:
        logger.error(f"failed to handle socks request from client {client_addr}: {err}")
    finally:
        await util.close_writer(writer)
    logger.debug(f"client {client_addr} disconnected")


async def start_socks_server(host: str, port: int) -> int:
    try:
        server = await asyncio.start_server(client_connected_cb, host, port)
    except Exception as err:
        print(f"{sys.argv[0]}: error: {err}", file=sys.stderr)
        return 1
    for sock in server.sockets:
        local_addr = util.format_addr(*sock.getsockname()[:2])
        print(f"Serving SOCKS on {local_addr}")
    util.init_logging()
    async with server:
        await server.serve_forever()
    return 0
