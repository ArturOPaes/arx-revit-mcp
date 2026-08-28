# -*- coding: utf-8 -*-
"""
Quando o Revit RECUSA fechar o grupo, a resposta não pode dizer que fechou.

A primeira versão de `_fechar` engolia a exceção e o handler já tinha em mãos
uma decisão pura com `ok=True` — então `/commit_job/` respondia 200,
`action: rollback`, "nothing persisted". Ou seja: o ensaio podia ter ficado no
modelo, e a única resposta afirmava o contrário.

Um revisor reproduziu com um adaptador que recusa o rollback, e os 136 testes
continuaram verdes, porque a suíte testava `JobGroups` — a parte pura — e não
este adaptador.
"""

import sys
import types

import pytest


@pytest.fixture
def rotas(monkeypatch):
    """`job_routes` com um pyRevit de mentira, para os handlers rodarem aqui."""
    respostas = []

    falso_routes = types.SimpleNamespace(
        make_response=lambda data=None, status=200: respostas.append((status, data)) or (status, data)
    )
    pyrevit = types.ModuleType("pyrevit")
    pyrevit.routes = falso_routes
    pyrevit.DB = types.SimpleNamespace(TransactionGroup=lambda doc, nome: FalsoGrupo())
    monkeypatch.setitem(sys.modules, "pyrevit", pyrevit)
    for m in list(sys.modules):
        if m.startswith("revit_mcp.job_routes"):
            del sys.modules[m]
    import importlib

    jr = importlib.import_module("revit_mcp.job_routes")
    importlib.reload(jr)
    return jr, respostas


class FalsoGrupo:
    recusa = False

    def Start(self):
        pass

    def Assimilate(self):
        if FalsoGrupo.recusa:
            raise RuntimeError("Revit refused assimilate")

    def RollBack(self):
        if FalsoGrupo.recusa:
            raise RuntimeError("Revit refused rollback")


class Pedido:
    def __init__(self, corpo):
        self.data = corpo


def test_o_revit_recusando_desfazer_nao_vira_sucesso(rotas):
    jr, respostas = rotas
    handlers = {}

    class Api:
        def route(self, caminho, methods=None):
            def registra(fn):
                handlers[caminho] = fn
                return fn

            return registra

    jr.register_job_routes(Api())
    FalsoGrupo.recusa = False
    handlers["/begin_job/"](None, Pedido({"job_id": "j1", "dry_run": True}))
    FalsoGrupo.recusa = True
    try:
        status, dados = handlers["/commit_job/"](None, Pedido({"job_id": "j1"}))
    finally:
        FalsoGrupo.recusa = False

    assert status == 500, f"o Revit recusou e a resposta saiu {status}"
    assert dados["ok"] is False
    assert "PODE" in dados["message"], f"a resposta não avisa que ficou no modelo: {dados}"
    assert "refused rollback" in dados.get("revit_error", "")


def test_quando_o_revit_aceita_a_resposta_continua_normal(rotas):
    jr, respostas = rotas
    handlers = {}

    class Api:
        def route(self, caminho, methods=None):
            def registra(fn):
                handlers[caminho] = fn
                return fn

            return registra

    jr.register_job_routes(Api())
    FalsoGrupo.recusa = False
    handlers["/begin_job/"](None, Pedido({"job_id": "j1"}))
    status, dados = handlers["/commit_job/"](None, Pedido({"job_id": "j1"}))

    assert status == 200
    assert dados["ok"] is True


def test_plano_com_passo_perdido_nao_sai_como_completo(rotas, monkeypatch):
    """A perda tem de chegar à RESPOSTA, não só ao log.

    Eu tinha testado que a perda fica registrada em `changes.passos_perdidos()`
    — a peça — e não que o `commit_job` faz alguma coisa com ela — o caminho.
    A mutação que apaga o `if perdidos:` passava em tudo.
    """
    jr, _ = rotas
    from revit_mcp import changes

    handlers = {}

    class Api:
        def route(self, caminho, methods=None):
            def registra(fn):
                handlers[caminho] = fn
                return fn

            return registra

    jr.register_job_routes(Api())
    FalsoGrupo.recusa = False
    handlers["/begin_job/"](None, Pedido({"job_id": "j1", "dry_run": True}))

    # Um passo se perdeu no caminho da soma.
    monkeypatch.setattr(changes, "passos_perdidos", lambda: ["/create_walls/"])

    status, dados = handlers["/commit_job/"](None, Pedido({"job_id": "j1"}))

    assert status == 409, f"o plano incompleto saiu como sucesso ({status})"
    assert dados["ok"] is False
    assert dados["plano_incompleto"] == ["/create_walls/"]
    assert "INCOMPLETO" in dados["message"], dados["message"]
    assert "não aprove" in dados["message"], "a resposta não diz o que NÃO fazer"


def test_plano_sem_perda_sai_completo(rotas):
    jr, _ = rotas
    handlers = {}

    class Api:
        def route(self, caminho, methods=None):
            def registra(fn):
                handlers[caminho] = fn
                return fn

            return registra

    jr.register_job_routes(Api())
    FalsoGrupo.recusa = False
    handlers["/begin_job/"](None, Pedido({"job_id": "j1", "dry_run": True}))
    status, dados = handlers["/commit_job/"](None, Pedido({"job_id": "j1"}))

    assert status == 200 and dados["ok"] is True
    assert "plano_incompleto" not in dados
