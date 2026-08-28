# -*- coding: utf-8 -*-
"""
As três rotas do grupo têm ferramenta que as exponha — e ela é CHAMÁVEL.

`revit_mcp/job_routes.py` registrava `/begin_job/`, `/commit_job/` e
`/abort_job/` dentro do pyRevit, e nenhum dos vinte e dois módulos de
ferramentas os expunha: o agente não conseguia abrir grupo nem pedir ensaio
nem se quisesse. Construído e inalcançável, medido por um revisor.

E o registro precisa passar os argumentos CERTOS. A primeira versão desta
ligação copiou a linha do módulo vizinho e passou só `revit_get` — a
ferramenta usa `revit_post`, e a falha só apareceria ao registrar, dentro do
Revit, longe daqui.
"""

import inspect

import pytest


class MCPFalso:
    """O suficiente para registrar ferramentas e guardar o que foi registrado."""

    def __init__(self):
        self.ferramentas = {}

    def tool(self, *_a, **_k):
        def registra(fn):
            self.ferramentas[fn.__name__] = fn
            return fn

        return registra


@pytest.fixture
def registradas():
    from tools import register_tools

    mcp = MCPFalso()
    chamadas = []

    async def get(endpoint, ctx=None, **kw):
        chamadas.append(("GET", endpoint, kw))
        return {}

    async def post(endpoint, data=None, ctx=None, **kw):
        chamadas.append(("POST", endpoint, data))
        return {"ok": True}

    async def imagem(endpoint, ctx=None):
        return ""

    register_tools(mcp, get, post, imagem)
    return mcp, chamadas


def test_as_tres_ferramentas_existem(registradas):
    mcp, _ = registradas
    for nome in ("begin_job", "commit_job", "abort_job"):
        assert nome in mcp.ferramentas, f"{nome} não foi exposta ao agente"


@pytest.mark.anyio
async def test_begin_job_chega_na_rota_certa_com_o_ensaio(registradas):
    mcp, chamadas = registradas
    await mcp.ferramentas["begin_job"]("job-1", dry_run=True)
    assert ("POST", "/begin_job/", {"job_id": "job-1", "dry_run": True}) in chamadas


@pytest.mark.anyio
async def test_commit_e_abort_chegam_nas_rotas_certas(registradas):
    mcp, chamadas = registradas
    await mcp.ferramentas["commit_job"]("job-1")
    await mcp.ferramentas["abort_job"]("job-1")
    caminhos = [c[1] for c in chamadas]
    assert "/commit_job/" in caminhos and "/abort_job/" in caminhos


def test_o_registro_recebe_o_que_a_ferramenta_usa(registradas):
    # A ligação copiada do módulo vizinho passava só `revit_get`, e a
    # ferramenta usa `revit_post`. Sem isto, a falha só apareceria dentro do
    # Revit — o lugar onde ninguém está olhando.
    from tools.job_tools import register_job_tools

    parametros = list(inspect.signature(register_job_tools).parameters)
    assert "revit_post" in parametros
    # E o registro real precisa ter passado o terceiro argumento: se não
    # tivesse, o fixture acima teria estourado ao montar as ferramentas.
    mcp, _ = registradas
    assert mcp.ferramentas["begin_job"] is not None


def test_a_ferramenta_avisa_que_o_ensaio_EXECUTA(registradas):
    # O texto que o agente lê é o que decide se ele usa a coisa certa. "Ensaio"
    # que parece inócuo faz alguém exportar um PDF achando que nada aconteceu.
    mcp, _ = registradas
    doc = mcp.ferramentas["begin_job"].__doc__ or ""
    assert "executes" in doc.lower(), doc
    assert "already left" in doc.lower(), doc
