"""A porta que devolve IMAGEM — a única das quatro sem rede de teste.

`revit_get`, `revit_post` e o cliente compartilhado já tinham prova; a
`revit_image` não, e ela é a que faz mais coisa: decodifica base64 e monta um
objeto `Image` que a agent CLI vai renderizar.

Cada erro dela vira TEXTO, como nas irmãs. Um `Error: ...` na conversa é ruim; a
exceção subindo mata o turno inteiro e o arquiteto perde o que já tinha sido
feito.
"""

import base64

import pytest


@pytest.mark.anyio
async def test_a_imagem_volta_decodificada(revit):
    """O caminho feliz: base64 entra, bytes saem."""
    original = b"\x89PNG\r\n\x1a\n-conteudo-de-teste"
    revit.responde("/view_image/", {"image_data": base64.b64encode(original).decode()})

    resultado = await revit.main.revit_image("/view_image/")

    assert not isinstance(resultado, str), f"virou texto em vez de imagem: {resultado}"
    assert resultado.data == original
    # O `Image` do MCP não expõe o formato como atributo — ele vira o MIME do
    # conteúdo na hora de mandar. Conferir ali é conferir o que a agent CLI
    # recebe, e não o que guardamos.
    assert resultado.to_image_content().mimeType == "image/png"
    assert revit.pedidos[-1]["caminho"] == "/revit_mcp/view_image/"


@pytest.mark.anyio
async def test_status_de_erro_vira_texto_com_o_corpo(revit):
    """O Revit recusou: o motivo dele sobrevive até a conversa.

    Devolver só "erro 500" faria o arquiteto abrir um chamado para descobrir o
    que o Revit já tinha dito.
    """
    revit.responde("/view_image/", "vista ativa nao suporta exportacao", status=500)

    resultado = await revit.main.revit_image("/view_image/")

    assert isinstance(resultado, str)
    assert "500" in resultado
    assert "vista ativa nao suporta exportacao" in resultado


@pytest.mark.anyio
async def test_revit_fechado_vira_texto_e_nao_excecao(revit):
    """Sem Revit não há soquete. A exceção subindo mataria o turno."""
    import httpx

    revit.cai(httpx.ConnectError("connection refused"))

    resultado = await revit.main.revit_image("/view_image/")

    assert isinstance(resultado, str)
    assert resultado.startswith("Error:")


@pytest.mark.anyio
async def test_corpo_sem_a_imagem_vira_texto(revit):
    """200 com o corpo errado é o caso que mais engana.

    A resposta "deu certo" e não tem `image_data`; sem esta rede, o `KeyError`
    subiria de dentro de um caminho que já tinha sido dado como bem-sucedido.
    """
    revit.responde("/view_image/", {"ok": True})

    resultado = await revit.main.revit_image("/view_image/")

    assert isinstance(resultado, str)
    assert resultado.startswith("Error:")


@pytest.mark.anyio
async def test_base64_quebrado_vira_texto(revit):
    """O campo veio, e não é base64. Mesma regra: texto, nunca exceção."""
    revit.responde("/view_image/", {"image_data": "isto-nao-e-base64-!!!"})

    resultado = await revit.main.revit_image("/view_image/")

    assert isinstance(resultado, str)
    assert resultado.startswith("Error:")
