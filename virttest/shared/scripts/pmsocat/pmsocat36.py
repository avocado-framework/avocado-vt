#!/usr/bin/env python3

import argparse
import asyncio
import os
import sys

_args = None


async def forward(reader, writer, prefix):
    total = 0
    while True:
        data = await reader.read(_args.blocksize)
        if not data:
            break
        new_tot = total + len(data)
        print(f"{ prefix }  length={ len(data) } from={ total } to={ new_tot - 1}")
        total = new_tot
        if _args.output:
            print(data.decode(encoding="ascii", errors="replace"))
        writer.write(data)
        await writer.drain()
    print(f"{ prefix } close")
    writer.close()


async def handle_tcp_conn(reader1, writer1):
    """
    Call back function of tcp2unix
    """
    loop = asyncio.get_running_loop()
    reader2, writer2 = await asyncio.open_unix_connection(_args.socket_path)
    loop.create_task(forward(reader1, writer2, ">"))
    loop.create_task(forward(reader2, writer1, "<"))


async def handle_unix_conn(reader1, writer1):
    """
    Call back function of unix2tcp
    """
    loop = asyncio.get_running_loop()
    reader2, writer2 = await asyncio.open_connection(_args.host, _args.port)
    loop.create_task(forward(reader1, writer2, ">"))
    loop.create_task(forward(reader2, writer1, "<"))


def tcp2unix():
    """
    A wrapper function to start a service that listens on network and
    connects to UNIX socket
    """
    return asyncio.start_server(handle_tcp_conn, _args.address, _args.port)


def unix2tcp():
    """
    A wrapper function to start a server that listens on UNIX socket and
    connects to network
    """
    if _args.selinux_context:
        import selinux

        if selinux.setsockcreatecon(_args.selinux_context) != 0:
            return 1
    try:
        os.unlink(_args.socket_path)
    except FileNotFoundError:
        pass
    ret = asyncio.start_unix_server(handle_unix_conn, _args.socket_path)
    if _args.selinux_context:
        selinux.setsockcreatecon(None)
    return ret


def main(loop):
    parser = argparse.ArgumentParser(
        description="Poor Man's Socat, but with a SELinux feature"
    )
    parser.add_argument(
        "-o",
        "--output",
        action="store_true",
        help="output forwarded data to stdout (WARNING: slows down everything)",
    )
    parser.add_argument(
        "-b",
        "--blocksize",
        help="Size of forwarded chunks in Bytes (default 1MB)",
        default=2**20,
        type=int,
    )
    parser.set_defaults(func=None)

    subparsers = parser.add_subparsers(title="functions", dest="function")

    tcp2unix_sp = subparsers.add_parser(
        "tcp2unix", help="listen on network and connect to UNIX socket"
    )
    tcp2unix_sp.add_argument(
        "-a", "--address", help='listen address (default "0.0.0.0")', default="0.0.0.0"
    )
    tcp2unix_sp.add_argument("port", help="port to listen on")
    tcp2unix_sp.add_argument("socket_path", help="UNIX socket path to connect to")
    tcp2unix_sp.set_defaults(func=tcp2unix)

    unix2tcp_sp = subparsers.add_parser(
        "unix2tcp", help="listen on UNIX socket and connect to network"
    )
    unix2tcp_sp.add_argument(
        "-c",
        "--selinux-context",
        help="SELinux context used for the listening UNIX socket path to listen on",
    )
    unix2tcp_sp.add_argument("socket_path", help="UNIX socket path to listen on")
    unix2tcp_sp.add_argument("host", help="connect to this host/address")
    unix2tcp_sp.add_argument("port", help="port to listen on")
    unix2tcp_sp.set_defaults(func=unix2tcp)

    global _args
    _args = parser.parse_args()
    if _args.func is None:
        parser.print_help()
        sys.exit(1)
    coro = _args.func()
    return loop.run_until_complete(coro)


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        loop = asyncio.get_event_loop()
    else:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)
    coro = main(loop)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    coro.close()
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.close()
