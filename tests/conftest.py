# -*- coding: utf-8 -*-
"""
A base de teste do fork — o que faltava para qualquer ticket deste mapa
entregar código COM SINAL.

# Por que um Routes falso, e não um Revit

`main.py` é o lado de fora: ele fala HTTP com o servidor pyRevit Routes que
roda dentro do Revit, em `127.0.0.1:48884`. Tudo o que ele faz — montar a
chamada, ler a resposta, decidir o que é erro — é exercitável sem Revit
nenhum, desde que alguém responda naquele endereço. É o que este arquivo faz.

O que ele NÃO prova: que uma transação commita, que um elemento nasce onde
devia, que a API do Revit aceita o payload. Isso só numa máquina com Revit — e
fingir o contrário seria pior que não ter teste, porque daria confiança falsa.
"""
import importlib
import json
import sys
from pathlib import Path

import httpx
import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


class RoutesFalso:
    """O servidor pyRevit Routes, respondendo do lado de cá.

    Guarda o que foi pedido — método, caminho, corpo — porque metade dos
    defeitos desta camada não está na resposta que ela lê, e sim na chamada
    que ela monta.
    """

    def __init__(self):
        self.respostas = {}
        self.pedidos = []
        self.erro_de_rede = None

    def responde(self, caminho, corpo, status=200):
        self.respostas[caminho] = (status, corpo)

    def cai(self, erro):
        """A rede falha — Revit fechado, porta trocada, tempo esgotado."""
        self.erro_de_rede = erro

    def _handler(self, request: httpx.Request) -> httpx.Response:
        corpo = None
        if request.content:
            try:
                corpo = json.loads(request.content)
            except ValueError:
                corpo = request.content.decode("utf-8", "replace")
        self.pedidos.append({
            "metodo": request.method,
            "caminho": request.url.path,
            "consulta": dict(request.url.params),
            "corpo": corpo,
        })
        if self.erro_de_rede is not None:
            raise self.erro_de_rede
        caminho = request.url.path.replace("/revit_mcp", "", 1) or "/"
        if caminho not in self.respostas:
            return httpx.Response(404, text="rota nao registrada no falso: " + caminho)
        status, corpo = self.respostas[caminho]
        if isinstance(corpo, (dict, list)):
            return httpx.Response(status, json=corpo)
        return httpx.Response(status, text=str(corpo))

    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handler)


@pytest.fixture
def revit(monkeypatch):
    """`main` ligado a um Revit de mentira, e nenhum soquete aberto.

    O cliente é trocado por um que fala com o transporte falso. O `main` real
    guarda o cliente numa variável de módulo e o reaproveita — por isso a
    troca é do `_get_client`, e não do cliente: é ele que decide quando criar
    um novo, e essa decisão também é código nosso.
    """
    import main as modulo

    modulo = importlib.reload(modulo)
    falso = RoutesFalso()
    cliente = httpx.AsyncClient(base_url=modulo.BASE_URL, transport=falso.transporte())
    monkeypatch.setattr(modulo, "_get_client", lambda: cliente)
    falso.main = modulo
    yield falso


@pytest.fixture
def anyio_backend():
    """Só asyncio: o `trio` não é dependência do fork, e deixar o padrão do
    anyio faria metade dos testes falhar por falta de um pacote que ninguém
    usa em produção."""
    return "asyncio"
