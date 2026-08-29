# -*- coding: utf-8 -*-
"""O código que a ponte diz ter executado atravessa inteiro até o cliente MCP.

O argumento da ferramenta é só o PEDIDO. A resposta da rota, já dentro do
Revit, é a única fonte que pode dizer o que realmente rodou.
"""

import json

import pytest


class MCPFalso:
    def __init__(self):
        self.ferramentas = {}

    def tool(self, *_args, **_kwargs):
        def registrar(fn):
            self.ferramentas[fn.__name__] = fn
            return fn

        return registrar


def ferramenta_com(resposta):
    from tools.code_execution_tools import register_code_execution_tools

    mcp = MCPFalso()

    async def post(_endpoint, _payload, _ctx=None):
        return resposta

    register_code_execution_tools(mcp, None, post)
    return mcp.ferramentas["execute_revit_code"]


@pytest.mark.anyio
async def test_registra_o_codigo_que_RODOU_e_nao_o_que_foi_pedido():
    executar = ferramenta_com(
        {
            "status": "success",
            "executed_at": "2026-08-29T18:03:04.123456Z",
            "code_executed": "print('o que RODOU')",
            "output": "feito",
        }
    )

    bruto = await executar("print('o que foi pedido')")
    registro = json.loads(bruto)

    assert registro["code_executed"] == "print('o que RODOU')"
    assert "o que foi pedido" not in bruto
    assert registro["executed_at"] == "2026-08-29T18:03:04.123456Z"


@pytest.mark.anyio
async def test_o_erro_inteiro_atravessa_em_vez_de_ser_engolido():
    traceback_inteiro = (
        "Traceback (most recent call last):\n"
        "  File \"<string>\", line 7, in <module>\n"
        "Autodesk.Revit.Exceptions.InvalidOperationException: detalhe final"
    )
    executar = ferramenta_com(
        {
            "status": "error",
            "executed_at": "2026-08-29T18:04:05.654321Z",
            "code_attempted": "raise Exception('quebrou')",
            "error": "InvalidOperationException: detalhe final",
            "error_type": "InvalidOperationException",
            "traceback": traceback_inteiro,
            "partial_output": "primeiro passo\n",
        }
    )

    bruto = await executar("pedido diferente")
    registro = json.loads(bruto)

    assert registro["status"] == "error"
    assert registro["traceback"] == traceback_inteiro
    assert registro["error"] == "InvalidOperationException: detalhe final"
    assert registro["partial_output"] == "primeiro passo\n"
