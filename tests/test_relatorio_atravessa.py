# -*- coding: utf-8 -*-
"""
O relatório de escrita atravessa o MCP sem ser reinterpretado.

O gate de aprovação do ARCHITECTUS decide sobre o `changes.json`, e a
conferência de norma reprova projeto com base nas medições que vêm dentro
dele. O relatório é do REVIT; o MCP é encanamento.

Se esta camada reescrevesse, arredondasse ou "melhorasse" qualquer coisa no
caminho, o número que reprova o projeto de alguém passaria a ter dois autores
— e o que a tela mostra como medido pela ponte teria passado por uma opinião
no meio.
"""
import pytest

from revit_mcp.changes import MEDIDA_PELA_PONTE, ChangeReport


def relatorio_de_exemplo():
    return (
        ChangeReport()
        .created(101, 102)
        .modified(7)
        .room(
            "sala-01",
            "dormitorio",
            {
                "area_piso_m2": 12.5,
                "iluminacao": {"valor": 1.5, "base": 12.5, "bruta": "1.5 m² / 12.5 m²"},
            },
            nome="Suíte",
        )
        .to_dict()
    )


@pytest.mark.anyio
async def test_o_relatorio_chega_identico_do_outro_lado(revit):
    relatorio = relatorio_de_exemplo()
    revit.responde("/create_walls/", {"success": True, "changes_report": relatorio})

    resposta = await revit.main.revit_post("/create_walls/", {"walls": []})

    # Idêntico, e não "equivalente": um float virando string, uma lista
    # reordenada ou uma chave a mais já são o MCP opinando sobre um fato do
    # Revit.
    assert resposta["changes_report"] == relatorio


@pytest.mark.anyio
async def test_a_procedencia_sobrevive_a_travessia(revit):
    # É o campo que separa "a ponte mediu" de "o agente declarou". Perdê-lo
    # aqui faria uma medição real chegar ao servidor como desconhecida — o
    # lado seguro, e que apaga justamente a prova que este caminho existe
    # para produzir.
    revit.responde("/rooms/", {"changes_report": relatorio_de_exemplo()})

    resposta = await revit.main.revit_get("/rooms/")

    medicoes = resposta["changes_report"]["measurements"]["ambientes"][0]["medicoes"]
    assert medicoes["area_piso_m2"]["procedencia"] == MEDIDA_PELA_PONTE
    assert medicoes["iluminacao"]["base"] == 12.5


@pytest.mark.anyio
async def test_rota_que_nao_muda_nada_atravessa_com_as_listas_vazias(revit):
    # E não com o campo ausente: "não mudei nada" e "não disse" são coisas
    # diferentes para o gate.
    vazio = {"created": [], "modified": [], "deleted": [], "measurements": {}}
    revit.responde("/model_info/", {"changes_report": vazio})

    resposta = await revit.main.revit_get("/model_info/")

    assert resposta["changes_report"] == vazio
    assert "created" in resposta["changes_report"]
