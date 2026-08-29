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


def _monta(jr):
    handlers = {}

    class Api:
        def route(self, caminho, methods=None):
            def registra(fn):
                handlers[caminho] = fn
                return fn

            return registra

    jr.register_job_routes(Api())
    return handlers


def test_abort_com_o_revit_recusando_nao_diz_descartado(rotas):
    """Mesma regra do commit, e ela faltava no abort.

    Um revisor mediu: `/abort_job/` respondia 200, "job a discarded", com o
    grupo ainda aberto no adaptador. Dizer "descartado" quando o Revit recusou
    desfazer é a única mentira que estas rotas não podem contar — o arquiteto
    segue achando que o modelo voltou.
    """
    jr, _ = rotas
    handlers = _monta(jr)
    FalsoGrupo.recusa = False
    handlers["/begin_job/"](None, Pedido({"job_id": "a"}))
    FalsoGrupo.recusa = True
    try:
        status, dados = handlers["/abort_job/"](None, Pedido({"job_id": "a"}))
    finally:
        FalsoGrupo.recusa = False

    assert status == 500, f"o abort saiu {status} com o Revit recusando"
    assert dados["ok"] is False
    assert "PODE" in dados["message"]


def test_begin_por_cima_de_um_grupo_que_nao_desfaz_nao_abre_outro(rotas):
    """Empilhar trabalho sobre um estado que ninguém sabe qual é.

    O `begin` de um trabalho novo descarta o anterior. Se o Revit recusar esse
    descarte e a rota abrir o novo mesmo assim, o segundo trabalho nasce em
    cima do primeiro — e nada, nem no modelo nem na resposta, diz isso.
    """
    jr, _ = rotas
    handlers = _monta(jr)
    FalsoGrupo.recusa = False
    handlers["/begin_job/"](None, Pedido({"job_id": "a"}))
    FalsoGrupo.recusa = True
    try:
        status, dados = handlers["/begin_job/"](None, Pedido({"job_id": "b"}))
    finally:
        FalsoGrupo.recusa = False

    assert status == 500, f"abriu o trabalho novo por cima do que não desfez ({status})"
    assert dados["ok"] is False


def test_o_revit_recusando_abrir_nao_deixa_trabalho_fantasma(rotas, monkeypatch):
    """`Start()` que falha deixava o trabalho registrado como aberto.

    A decisão pura é tomada antes do efeito. Sem compensar, o `begin` seguinte
    respondia "já está aberto" sobre um grupo que nunca começou — e o trabalho
    inteiro rodaria sem grupo nenhum, achando que tinha um.
    """
    jr, _ = rotas
    handlers = _monta(jr)

    class NaoAbre(FalsoGrupo):
        def Start(self):
            raise RuntimeError("start refused")

    monkeypatch.setattr(jr.DB, "TransactionGroup", lambda doc, nome: NaoAbre())

    status, dados = handlers["/begin_job/"](None, Pedido({"job_id": "d"}))
    assert status == 500 and dados["ok"] is False

    # E o trabalho não ficou registrado: o próximo begin ABRE, não diz "já está
    # aberto".
    monkeypatch.setattr(jr.DB, "TransactionGroup", lambda doc, nome: FalsoGrupo())
    FalsoGrupo.recusa = False
    status, dados = handlers["/begin_job/"](None, Pedido({"job_id": "d"}))
    assert dados["action"] == "open", f"trabalho fantasma: {dados}"


def test_falha_transitoria_pode_ser_tentada_de_novo(rotas):
    """Jogar fora a referência não torna o estado seguro; torna-o irrecuperável.

    Um revisor mediu: o primeiro `abort` recusado devolvia 500 e apagava o
    dono; o segundo, com o Revit já aceitando, respondia "no job is open" — e
    a única referência para fechar o grupo tinha sumido.
    """
    jr, _ = rotas
    handlers = _monta(jr)
    FalsoGrupo.recusa = False
    handlers["/begin_job/"](None, Pedido({"job_id": "a"}))

    FalsoGrupo.recusa = True
    status, _ = handlers["/abort_job/"](None, Pedido({"job_id": "a"}))
    assert status == 500

    # A recusa passou. A segunda tentativa tem de FUNCIONAR.
    FalsoGrupo.recusa = False
    status, dados = handlers["/abort_job/"](None, Pedido({"job_id": "a"}))
    assert status == 200, f"a segunda tentativa não achou o trabalho: {dados}"
    assert dados["action"] == "rollback"


def test_o_start_que_falha_no_ramo_de_substituicao_tambem_e_tratado(rotas, monkeypatch):
    """O `try` cobria só o primeiro `begin`.

    Um revisor mediu: `a` abre, o rollback de `a` funciona, o `Start()` de `b`
    levanta — a exceção escapava, o dono já era `b`, e o `begin b` seguinte
    respondia "já está aberto" sobre um grupo que nunca abriu.
    """
    jr, _ = rotas
    handlers = _monta(jr)
    FalsoGrupo.recusa = False
    handlers["/begin_job/"](None, Pedido({"job_id": "a"}))

    class NaoAbre(FalsoGrupo):
        def Start(self):
            raise RuntimeError("start refused")

    monkeypatch.setattr(jr.DB, "TransactionGroup", lambda doc, nome: NaoAbre())
    status, dados = handlers["/begin_job/"](None, Pedido({"job_id": "b"}))
    assert status == 500 and dados["ok"] is False

    # E `b` não ficou registrado: o próximo begin ABRE.
    monkeypatch.setattr(jr.DB, "TransactionGroup", lambda doc, nome: FalsoGrupo())
    status, dados = handlers["/begin_job/"](None, Pedido({"job_id": "b"}))
    assert dados["action"] == "open", f"trabalho fantasma no ramo de substituição: {dados}"


def test_a_perda_do_trabalho_anterior_sobrevive_a_um_begin_que_falha(rotas, monkeypatch):
    """A evidência era apagada antes de saber se o novo trabalho começou.

    Reprodução do revisor: perda registrada em `a`, o rollback de `a` recusa,
    o `begin b` volta 500 — e `passos_perdidos()` voltava vazio. A perda de
    `a` era destruída, e o plano dele passaria a se apresentar como completo.
    """
    jr, _ = rotas
    from revit_mcp import changes

    handlers = _monta(jr)
    FalsoGrupo.recusa = False
    handlers["/begin_job/"](None, Pedido({"job_id": "a", "dry_run": True}))

    # A entrega do passo falha — é o caso que produz perda. Aqui o
    # `job_routes` é importável (o pyRevit é de mentira), então a falha
    # precisa ser provocada.
    def recusa(*_a, **_k):
        raise RuntimeError("collector offline")

    monkeypatch.setattr(jr, "record_change", recusa)
    changes.registrar_no_trabalho({}, "/create_walls/")
    assert changes.passos_perdidos() == ["/create_walls/"]

    FalsoGrupo.recusa = True
    try:
        status, _ = handlers["/begin_job/"](None, Pedido({"job_id": "b"}))
    finally:
        FalsoGrupo.recusa = False

    assert status == 500
    assert changes.passos_perdidos() == ["/create_walls/"], (
        "a perda do trabalho anterior foi apagada antes de o novo começar"
    )


def test_o_commit_recusado_tambem_pode_ser_tentado_de_novo(rotas):
    # A mesma regra do abort, no caminho que de fato importa: um trabalho de
    # verdade cuja assimilação falha não pode perder a referência — é o
    # trabalho do arquiteto que fica no limbo.
    jr, _ = rotas
    handlers = _monta(jr)
    FalsoGrupo.recusa = False
    handlers["/begin_job/"](None, Pedido({"job_id": "a"}))

    FalsoGrupo.recusa = True
    status, _ = handlers["/commit_job/"](None, Pedido({"job_id": "a"}))
    assert status == 500

    FalsoGrupo.recusa = False
    status, dados = handlers["/commit_job/"](None, Pedido({"job_id": "a"}))
    assert status == 200, f"a segunda tentativa de confirmar não achou o trabalho: {dados}"
    assert dados["action"] == "assimilate"


def test_um_trabalho_novo_comeca_sem_as_perdas_do_anterior(rotas, monkeypatch):
    # O outro lado do teste acima: quando o begin dá certo, a evidência do
    # trabalho anterior tem de sair — senão o plano do novo nasce carregando
    # uma incompletude que não é dele.
    jr, _ = rotas
    from revit_mcp import changes

    handlers = _monta(jr)
    FalsoGrupo.recusa = False
    handlers["/begin_job/"](None, Pedido({"job_id": "a", "dry_run": True}))

    def recusa(*_a, **_k):
        raise RuntimeError("collector offline")

    monkeypatch.setattr(jr, "record_change", recusa)
    changes.registrar_no_trabalho({}, "/create_walls/")
    assert changes.passos_perdidos() == ["/create_walls/"]

    monkeypatch.undo()
    status, _ = handlers["/begin_job/"](None, Pedido({"job_id": "b", "dry_run": True}))
    assert status == 200
    assert changes.passos_perdidos() == [], "o trabalho novo herdou a perda do anterior"


def test_a_restauracao_devolve_o_ENSAIO_e_o_relatorio_inteiros(rotas, monkeypatch):
    """A compensação restaurava metade, e nenhum teste via.

    Um revisor removeu de `restaurar` a reposição de `dry_run`, `_reports` e
    `_routes`, e os 191 testes passaram. Na sequência real, depois da falha de
    substituição, o `commit` do ensaio respondia `assimilate` — **um ensaio
    seria tornado permanente e o relatório dele sumiria.**

    Este teste percorre a sequência inteira: ensaio com relatório e com efeito
    que não se desfaz, substituição recusada, e segunda tentativa.
    """
    jr, _ = rotas
    from revit_mcp import changes

    handlers = _monta(jr)
    FalsoGrupo.recusa = False
    handlers["/begin_job/"](None, Pedido({"job_id": "a", "dry_run": True}))

    # O trabalho `a` acumula relatório e um efeito que o rollback não desfaz.
    jr.record_change(
        {"created": ["7"], "modified": [], "deleted": [], "measurements": {}},
        route="/export_ifc/",
    )

    # E perde um passo pelo caminho.
    def recusa(*_a, **_k):
        raise RuntimeError("collector offline")

    monkeypatch.setattr(jr, "record_change", recusa)
    changes.registrar_no_trabalho({}, "/create_walls/")
    monkeypatch.undo()

    # A substituição por `b` é recusada pelo Revit.
    FalsoGrupo.recusa = True
    try:
        status, _ = handlers["/begin_job/"](None, Pedido({"job_id": "b"}))
    finally:
        FalsoGrupo.recusa = False
    assert status == 500

    # `a` voltou INTEIRO: ainda é ensaio, ainda tem o relatório, ainda sabe da
    # perda.
    status, dados = handlers["/commit_job/"](None, Pedido({"job_id": "a"}))
    assert dados["action"] == "rollback", (
        "o ensaio virou trabalho de verdade na volta: seria tornado permanente"
    )
    assert status == 409, "o plano incompleto voltou a se apresentar como completo"
    assert dados["plano_incompleto"] == ["/create_walls/"]
    assert dados["changes_report"]["created"] == ["7"], "o relatório sumiu na volta"
    assert "not_undone" in dados["changes_report"], "o aviso do que não se desfaz sumiu"


def test_o_instantaneo_e_tirado_ANTES_da_decisao(rotas, monkeypatch):
    """Fotografar depois da decisão restaura o estado já mudado.

    Um revisor moveu a foto para depois do `begin` e os 191 testes passaram.
    Na sequência real, a segunda tentativa respondia "job b is already open"
    enquanto o grupo de `a` continuava lá.
    """
    jr, _ = rotas
    handlers = _monta(jr)
    FalsoGrupo.recusa = False
    handlers["/begin_job/"](None, Pedido({"job_id": "a"}))

    FalsoGrupo.recusa = True
    try:
        handlers["/begin_job/"](None, Pedido({"job_id": "b"}))
    finally:
        FalsoGrupo.recusa = False

    # O dono tem de ser `a` de novo — e não `b`, que nunca chegou a abrir.
    status, dados = handlers["/begin_job/"](None, Pedido({"job_id": "b"}))
    assert dados["action"] == "rollback_then_open", (
        "a segunda tentativa achou que `b` já estava aberto: a foto foi tirada "
        "depois da decisão, e restaurou o estado já mudado ({})".format(dados)
    )
