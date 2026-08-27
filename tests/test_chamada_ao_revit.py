# -*- coding: utf-8 -*-
"""
A camada que fala com o Revit: o que ela manda, e o que ela faz com a resposta.

Primeira suíte do fork que roda SEM Revit — e sem Windows.
"""
import httpx
import pytest


@pytest.mark.anyio
async def test_get_devolve_o_corpo_decodificado(revit):
    revit.responde("/status/", {"status": "active", "revit_available": True})

    resposta = await revit.main.revit_get("/status/")

    assert resposta == {"status": "active", "revit_available": True}
    assert revit.pedidos[0]["metodo"] == "GET"
    assert revit.pedidos[0]["caminho"].endswith("/status/")


@pytest.mark.anyio
async def test_post_manda_json_e_o_cabecalho_certo(revit):
    revit.responde("/criar/", {"ok": True})

    await revit.main.revit_post("/criar/", {"nome": "Parede", "altura": 2.8})

    pedido = revit.pedidos[0]
    assert pedido["metodo"] == "POST"
    assert pedido["corpo"] == {"nome": "Parede", "altura": 2.8}


@pytest.mark.anyio
async def test_parametros_de_consulta_chegam_no_get(revit):
    revit.responde("/elementos/", [])

    await revit.main.revit_get("/elementos/", params={"categoria": "Walls", "limite": "50"})

    assert revit.pedidos[0]["consulta"] == {"categoria": "Walls", "limite": "50"}


# ————————————————————————————————————————————————————————————————
# Os caminhos de erro. É onde esta camada mais decide, e onde ela decide de um
# jeito que o teste tem de deixar registrado.
# ————————————————————————————————————————————————————————————————


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 404, 500, 503])
async def test_erro_do_revit_vira_TEXTO_e_nao_excecao(revit, status):
    """Uma recusa do Revit não levanta: ela volta como STRING começando por
    "Error:".

    Isto não é o desenho que a gente escolheria — quem chama não tem como
    distinguir um resultado de um fracasso a não ser olhando o texto, e um
    endpoint que legitimamente devolvesse a palavra "Error" enganaria todo
    mundo. Mas é o desenho que existe, e o gate de aprovação do ARCHITECTUS
    depende dele: fixá-lo aqui é o que permite mudá-lo de propósito depois, em
    vez de por acidente.
    """
    revit.responde("/status/", "documento fechado", status=status)

    resposta = await revit.main.revit_get("/status/")

    assert isinstance(resposta, str)
    assert resposta.startswith("Error: {}".format(status))
    assert "documento fechado" in resposta


@pytest.mark.anyio
async def test_revit_fechado_vira_texto_tambem(revit):
    """Nenhum servidor na porta 48884 — o caso mais comum de todos, porque o
    Revit passa a maior parte do tempo fechado."""
    revit.cai(httpx.ConnectError("connection refused"))

    resposta = await revit.main.revit_get("/status/")

    assert isinstance(resposta, str)
    assert resposta.startswith("Error:")
    assert "refused" in resposta


@pytest.mark.anyio
async def test_tempo_esgotado_vira_texto(revit):
    revit.cai(httpx.ReadTimeout("timed out"))

    resposta = await revit.main.revit_get("/lento/")

    assert isinstance(resposta, str)
    assert resposta.startswith("Error:")


@pytest.mark.anyio
async def test_corpo_que_nao_e_json_vira_texto_em_vez_de_estourar(revit):
    """Status 200 com corpo quebrado. Acontece quando o Routes devolve uma
    página de erro do servidor com 200 — e sem esta guarda o `.json()` estoura
    dentro da tool, longe de quem poderia entender o que houve."""
    revit.responde("/status/", "<html>nao sou json</html>")

    resposta = await revit.main.revit_get("/status/")

    assert isinstance(resposta, str)
    assert resposta.startswith("Error:")
