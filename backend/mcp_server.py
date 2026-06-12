# Entrypoint shim: .mcp.json invokes this file from the repo root.
import asyncio

from allworth_api.mcp import main

if __name__ == "__main__":
    asyncio.run(main())
