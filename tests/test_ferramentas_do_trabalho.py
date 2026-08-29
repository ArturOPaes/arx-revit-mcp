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


@pytest.mark.anyio
async def test_o_relatorio_do_ensaio_chega_ao_agente(registradas):
    """O que a ferramenta devolve é o plano. Perder o relatório aqui é perder
    tudo — e era o que acontecia: `format_response` devolve `message` assim que
    ela existe, e o resto do corpo some. Um `commit_job` de ensaio voltava como
    "rehearsal undone; nothing persisted", sem os elementos e sem as medições.

    O dublê da primeira versão deste arquivo devolvia `{"ok": true}`, então o
    teste passava sobre uma resposta que não tinha o que perder. Um revisor
    mediu no mesmo dia em que a ligação entrou.
    """
    import json as _json

    from tools import register_tools

    mcp = MCPFalso()

    async def get(endpoint, ctx=None, **kw):
        return {}

    async def post(endpoint, data=None, ctx=None, **kw):
        return {
            "ok": True,
            "action": "rollback",
            "message": "rehearsal of job j1 undone; nothing persisted",
            "changes_report": {
                "created": ["7"],
                "modified": [],
                "deleted": [],
                "measurements": {
                    "ambientes": [{"id": "sala-01", "uso": "dormitorio", "medicoes": {}}]
                },
            },
        }

    async def imagem(endpoint, ctx=None):
        return ""

    register_tools(mcp, get, post, imagem)
    saida = await mcp.ferramentas["commit_job"]("j1")

    assert "changes_report" in saida, f"o plano do ensaio não chegou ao agente: {saida}"
    assert "7" in saida, "o elemento sumiu do plano"
    assert "sala-01" in saida, "a medição sumiu do plano — é ela que a norma confere"
    _json.loads(saida)


def test_a_ferramenta_avisa_que_o_ensaio_EXECUTA(registradas):
    # O texto que o agente lê é o que decide se ele usa a coisa certa. "Ensaio"
    # que parece inócuo faz alguém exportar um PDF achando que nada aconteceu.
    mcp, _ = registradas
    doc = mcp.ferramentas["begin_job"].__doc__ or ""
    assert "executes" in doc.lower(), doc
    assert "already left" in doc.lower(), doc
