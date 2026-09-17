from __future__ import annotations

import asyncio
import base64
from urllib.parse import urlsplit

import pytest

from scrapingarena.scrapers.agent_browser_proxy import ProxyBridge
from scrapingarena.settings import ProxySettings


@pytest.mark.parametrize("tunnel", [False, True])
async def test_bridge_authenticates_and_relays(tunnel: bool) -> None:
    received = asyncio.get_running_loop().create_future()

    async def upstream(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            received.set_result(await reader.readuntil(b"\r\n\r\n"))
            if tunnel:
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
                writer.write(await reader.readexactly(4))
            else:
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\ndata")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(upstream, "127.0.0.1", 0)
    async with server:
        proxy = ProxySettings(
            "127.0.0.1",
            server.sockets[0].getsockname()[1],
            "customer-test-cc-US",
            "p/@:%ss",
            "test",
            "https://example.com",
        )
        bridge = ProxyBridge(proxy)
        try:
            url = urlsplit(await bridge.start())
            reader, writer = await asyncio.open_connection(url.hostname, url.port)
            first = b"CONNECT example.com:443" if tunnel else b"GET http://example.com/"
            writer.write(
                first + b" HTTP/1.1\r\nHost: example.com\r\n"
                b"Proxy-Authorization: Basic wrong\r\n\r\n"
            )
            await writer.drain()
            header = await asyncio.wait_for(received, 2)
            auth = base64.b64encode(b"customer-test-cc-US:p/@:%ss")
            assert b"Proxy-Authorization: Basic " + auth in header
            assert b"wrong" not in header
            if tunnel:
                assert b"200" in await reader.readuntil(b"\r\n\r\n")
                writer.write(b"data")
                await writer.drain()
                assert await reader.readexactly(4) == b"data"
            else:
                assert b"Connection: close" in header
                assert (await reader.read()).endswith(b"data")
            writer.close()
            await writer.wait_closed()
        finally:
            await bridge.close()
        assert not bridge.tasks
