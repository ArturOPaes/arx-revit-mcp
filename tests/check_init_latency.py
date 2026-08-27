# NÃO é teste de pytest — é diagnóstico manual, e exige Revit rodando.
#
# Renomeado de `test_*.py` para `check_*.py` em 27/08/2026: o corpo deste
# arquivo chama `asyncio.run(main())` no NÍVEL DE MÓDULO, então ele executava
# na COLETA do pytest e derrubava a suíte inteira antes de qualquer teste rodar:
#
#     AssertionError: expected model data missing
#     Interrupted: 1 error during collection
#
# Com o nome antigo, `pytest tests/` era impossível — inclusive num CI. O erro
# não era dos testes, e era neles que se procurava.
#
# Rode à mão: python tests/check_init_latency.py

# Measures time from spawn to MCP initialize response over stdio.
import asyncio, time, sys, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PY = sys.executable
MAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")

async def main():
    t0 = time.time()
    params = StdioServerParameters(command=PY, args=[MAIN])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            dt = time.time() - t0
            print("INIT_LATENCY_S=%.3f" % dt)
            # Floor (~0.9s on dev hw) is the required import cost of mcp.server.fastmcp
            # (~426ms) + httpx (~290ms, pulled in transitively by mcp anyway). No
            # non-essential import dominates, so there is nothing worth lazy-loading.
            # Threshold allows headroom for slower machines / CI.
            assert dt < 2.0, "initialize too slow: %.3f s" % dt

asyncio.run(main())
