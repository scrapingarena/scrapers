"""Exercise the same direct/proxy fixtures for the native browser adapters."""

import argparse
import asyncio

from smoke_vercel_agent_browser import smoke

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scraper", required=True, choices=["patchright", "moli"])
    parser.add_argument("--proxy", choices=["direct", "oxylabs"], default="direct")
    args = parser.parse_args()
    asyncio.run(smoke(args.proxy, args.scraper))
