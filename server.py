import asyncio
import sys
from argparse import ArgumentParser, ArgumentTypeError

import socks

__version__ = "0.1.1"


def port_type(port_str: str) -> int:
    try:
        port = int(port_str)
    except ValueError:
        raise ArgumentTypeError(f"invalid port number: {port_str}")
    if not 1 <= port <= 0xFFFF:
        raise ArgumentTypeError("port number should must be between 1 and 65535")
    return port


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-b",
        "--bind",
        help="specify bind address [default: all interfaces]",
        metavar="ADDRESS",
    )
    parser.add_argument(
        "port",
        nargs="?",
        default=1080,
        type=port_type,
        help="specify bind port [default: %(default)d]",
        metavar="PORT",
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(socks.start_socks_server(args.bind, args.port)))
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, exiting.")
        sys.exit(130)
