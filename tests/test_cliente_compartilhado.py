# -*- coding: utf-8 -*-
"""
O cliente HTTP é UM só, guardado no módulo e reaproveitado.

A razão está escrita no `main.py`: criar um cliente por chamada paga o custo
de TCP e handshake a cada tool, e uma sessão dispara dezenas delas. O que não
está escrito — e é o que estes testes fixam — é o que acontece quando esse
cliente morre.
"""
import importlib

import pytest


@pytest.fixture
def main_limpo(monkeypatch):
    import main as modulo

    modulo = importlib.reload(modulo)
    monkeypatch.setattr(modulo, "_http_client", None)
    return modulo


def test_o_mesmo_cliente_atende_todas_as_chamadas(main_limpo):
    assert main_limpo._get_client() is main_limpo._get_client()


@pytest.mark.anyio
async def test_cliente_fechado_e_substituido_em_vez_de_reusado(main_limpo):
    """Um cliente fechado não volta a funcionar: reusá-lo faria toda tool
    seguinte falhar até alguém reiniciar o servidor."""
    primeiro = main_limpo._get_client()
    await primeiro.aclose()

    segundo = main_limpo._get_client()

    assert segundo is not primeiro
    assert not segundo.is_closed


def test_o_endereco_do_revit_sai_do_ambiente(monkeypatch):
    """`REVIT_HOST` existe para apontar o servidor a outra máquina. É lido no
    IMPORT, então trocar a variável com o módulo já carregado não tem efeito —
    o teste fixa isso para ninguém depurar às cegas depois."""
    import main as modulo

    monkeypatch.setenv("REVIT_HOST", "10.0.0.7")
    recarregado = importlib.reload(modulo)

    assert recarregado.BASE_URL == "http://10.0.0.7:48884/revit_mcp"
    assert recarregado.REVIT_PORT == 48884
