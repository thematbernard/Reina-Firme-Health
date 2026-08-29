"""Start a fresh MCP server over stdio and print what it reports.

Pre-demo check: confirms the server starts, which warehouse it resolved, and the
build fingerprint it will advertise to a client. Compare the [build ...] value
against `make fingerprint`.

Note this spawns a NEW server, so it always reflects the code on disk. It tells
you what a client *should* see after restarting — it cannot tell you what an
already-running client is serving. For that, ask the client itself.

Run:  make server-info
"""

import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).parent.parent


async def probe() -> tuple[str, list[str]]:
    params = StdioServerParameters(
        command=sys.executable, args=[str(ROOT / "mcp_server" / "server.py")],
        cwd=str(ROOT),
    )
    with anyio.fail_after(60):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return session.instructions or "", [t.name for t in tools.tools]


def main():
    instructions, tools = anyio.run(probe)
    print("server instructions as a client will receive them:\n")
    print(instructions)
    print(f"\ntools advertised: {', '.join(sorted(tools))}")

    sys.path.insert(0, str(ROOT / "mcp_server"))
    import server

    print(f"\nwarehouse:   {server.DB}")
    print(f"mode:        {server.DB_MODE}")
    print(f"fingerprint: {server.build_fingerprint()}  (must match `make fingerprint`)")


if __name__ == "__main__":
    main()
