"""Per-attempt HTTP proxy bridge for agent-browser's native auth workaround."""

from __future__ import annotations

import asyncio
import base64
import contextlib

from scrapingarena.settings import ProxySettings


class ProxyBridge:
    """Authenticate upstream without enabling Chrome Fetch interception.

    CONNECT tunnels remain opaque; ordinary HTTP connections are closed after
    each response so every request receives upstream proxy authentication.
    """

    def __init__(self, proxy: ProxySettings) -> None:
        self.proxy = proxy
        self.server: asyncio.Server | None = None
        self.tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> str:
        self.server = await asyncio.start_server(self._accept, "127.0.0.1", 0)
        port = self.server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.create_task(self._forward(reader, writer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _forward(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        upstream: asyncio.StreamWriter | None = None
        pumps: list[asyncio.Task[None]] = []
        try:
            async with asyncio.timeout(30):
                header = await reader.readuntil(b"\r\n\r\n")
                lines = header[:-4].split(b"\r\n")
                tunnel = lines[0].startswith(b"CONNECT ")
                lines = [lines[0]] + [
                    line
                    for line in lines[1:]
                    if line.split(b":", 1)[0].lower()
                    not in {b"proxy-authorization", b"proxy-connection", b"connection"}
                ]
                credentials = base64.b64encode(
                    f"{self.proxy.username}:{self.proxy.password}".encode()
                )
                lines.append(b"Proxy-Authorization: Basic " + credentials)
                if not tunnel:
                    lines.extend([b"Connection: close", b"Proxy-Connection: close"])
                remote, upstream = await asyncio.open_connection(
                    self.proxy.host, self.proxy.port
                )
                upstream.write(b"\r\n".join(lines) + b"\r\n\r\n")
                await upstream.drain()

            async def copy(
                src: asyncio.StreamReader, dst: asyncio.StreamWriter
            ) -> None:
                while data := await src.read(65536):
                    dst.write(data)
                    await dst.drain()

            pumps = [
                asyncio.create_task(copy(reader, upstream)),
                asyncio.create_task(copy(remote, writer)),
            ]
            await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
        except (
            OSError,
            TimeoutError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ):
            # Do not expose upstream credentials in daemon errors or logs.
            if not writer.is_closing():
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                with contextlib.suppress(OSError):
                    await writer.drain()
        finally:
            for task in pumps:
                task.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)
            for connection in (writer, upstream):
                if connection is not None:
                    connection.close()
                    with contextlib.suppress(OSError):
                        await connection.wait_closed()

    async def close(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
