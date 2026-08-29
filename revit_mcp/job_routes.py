# -*- coding: UTF-8 -*-
"""
The three routes that wrap a whole job in one undo.

``DB.TransactionGroup`` lets the inner transactions commit and still be undone
together afterwards. That is the fine undo the ARCHITECTUS gate has been
missing: today its only fallback is to close the document and swap the file
back, which is blunt, loses everything that came after, and does not reach the
document open in memory.

All the *deciding* — what to do when a begin arrives with a group already
open, when a commit names a job that is not the open one, when a commit
arrives with nothing open — lives in ``job_group``, which has no Revit in it
and is covered by the suite that runs on any machine. What is left here is
three Revit calls and the plumbing.

Lifecycle, as decided:

- ``POST /begin_job/`` ``{"job_id": "..."}`` — opens the group. A begin for a
  *different* job discards the one left open first, and says which.
- ``POST /commit_job/`` ``{"job_id": "..."}`` — assimilates: the whole job
  becomes one undo entry in Revit.
- ``POST /abort_job/`` ``{"job_id": "..."}`` — rolls the group back.

There is **no timer**. If the agent dies mid-job, nothing runs on its own: the
next begin cleans up. The cost is written down rather than hidden — a model
can sit with an open group until someone calls again.
"""

from pyrevit import routes, DB
import json
import logging

from . import changes
from .job_group import (
    ASSIMILATE,
    NOTHING as NADA,
    OPEN,
    ROLLBACK,
    ROLLBACK_THEN_OPEN,
    JobGroups,
)

logger = logging.getLogger(__name__)

# One per Revit session. pyRevit Routes runs in-process inside Revit, so this
# survives between calls — which is exactly why the MCP being stateless does
# not stop us: the state that matters is on the Revit side.
_grupos = JobGroups()
_grupo_aberto = None


def _instantaneo():
    """Tudo o que precisa voltar se a chamada ao Revit recusar.

    Um só, e não uma tupla posicional repetida em três handlers — um revisor
    mostrou que a compensação vivia em três cópias e que isso é o que a torna
    fácil de restaurar pela metade.

    ## O que NÃO entra aqui, e por quê

    As perdas de `changes` não entram. Elas viveriam num segundo lugar, e a
    tentação é capturá-las "por segurança" — mas `esquecer_perdas` só roda
    depois de o grupo novo abrir de verdade, então numa chamada recusada não
    há perda nenhuma a devolver. Compensação para um caso que não acontece é
    pior que nenhuma: ela sugere uma cobertura que não existe, e o teste que a
    exercitaria não pode ser escrito.

    Quem mover `esquecer_perdas` para antes do `Start` faz
    `test_a_perda_do_trabalho_anterior_sobrevive_a_um_begin_que_falha` ficar
    vermelho — é ali que essa regra é guardada, e não aqui.
    """
    return _grupos.instantaneo()


def _restaurar(instantaneo):
    _grupos.restaurar(*instantaneo)


def _corpo(request):
    try:
        dados = request.data
        if isinstance(dados, str):
            dados = json.loads(dados)
        return dados or {}
    except Exception:
        return {}


def _abrir(doc, job_id):
    """Abre o grupo. Se o Revit recusar, o trabalho NÃO fica registrado.

    A decisão pura é tomada antes do efeito, e sem isto uma falha de `Start()`
    deixava um trabalho fantasma: `open_job` apontando para um grupo que nunca
    começou, e o `begin` seguinte respondendo "já está aberto". Um revisor
    reproduziu.
    """
    global _grupo_aberto
    grupo = DB.TransactionGroup(doc, "PlanArchi job {}".format(job_id))
    grupo.Start()
    _grupo_aberto = grupo


def _fechar(assimilar):
    """Assimilate or roll back. Devolve o erro do Revit, ou None.

    Quando a chamada ao Revit FALHA, o grupo FICA — e o erro sobe. Duas
    versões anteriores erravam aqui, cada uma de um jeito: a primeira engolia a
    exceção e respondia "nada persistiu" com o ensaio possivelmente no modelo;
    a segunda subia o erro mas esquecia o grupo, e com ele a única referência
    para tentar de novo. Uma falha transitória virava estado irrecuperável.

    Esta docstring já disse que esquecer era deliberado. Não é, e a linha ficou
    contradizendo o código por uma rodada inteira — um revisor apontou.
    """
    global _grupo_aberto
    grupo = _grupo_aberto
    if grupo is None:
        _grupo_aberto = None
        return None
    try:
        if assimilar:
            grupo.Assimilate()
        else:
            grupo.RollBack()
    except Exception as e:
        # O grupo FICA. Uma falha pode ser transitória, e apagar a referência
        # transforma "tente de novo" em "não há mais como tentar".
        logger.warning("job group could not be closed: %s", e)
        return str(e)
    _grupo_aberto = None
    return None


def _falhou_ao_fechar(dados, erro, assimilar):
    """A resposta deixa de afirmar o que não aconteceu."""
    dados["ok"] = False
    dados["revit_error"] = erro
    dados["message"] = (
        "o Revit recusou {} o grupo deste trabalho ({}). O que foi feito PODE "
        "ter ficado no modelo — confira antes de seguir."
    ).format("assimilar" if assimilar else "desfazer", erro)
    return dados


def record_change(changes_report, route=None):
    """Uma rota de escrita rodou. Guarda o que ela mudou, para o ensaio somar.

    Chamada pelas próprias rotas, e de propósito fora do `api.route`: o que
    interessa é o relatório que ela já monta, não interceptar a resposta.
    """
    _grupos.record(changes_report, route=route)


def register_job_routes(api):
    @api.route("/begin_job/", methods=["POST"])
    def begin_job_handler(doc, request):
        corpo = _corpo(request)
        job_id = corpo.get("job_id")
        antes = _instantaneo()
        decisao = _grupos.begin(job_id, dry_run=bool(corpo.get("dry_run")))
        if decisao.action == ROLLBACK_THEN_OPEN:
            erro = _fechar(assimilar=False)
            if erro:
                # O grupo anterior NÃO foi desfeito. Abrir outro por cima
                # empilharia trabalho sobre um estado que ninguém sabe qual é —
                # e o trabalho anterior volta a existir, com as perdas dele,
                # para que a segunda tentativa tenha o que fechar.
                _restaurar(antes)
                dados = _falhou_ao_fechar(decisao.to_dict(), erro, False)
                return routes.make_response(data=dados, status=500)
        if decisao.action in (OPEN, ROLLBACK_THEN_OPEN):
            try:
                _abrir(doc, job_id)
            except Exception as e:
                # O Revit recusou abrir. O trabalho não pode ficar registrado
                # como aberto — e o anterior, que já foi desfeito, também não
                # volta: ele não existe mais no Revit.
                _grupos.forget()
                return routes.make_response(
                    data={
                        "action": NADA,
                        "ok": False,
                        "message": "o Revit recusou abrir o grupo deste trabalho ({})".format(e),
                        "revit_error": str(e),
                    },
                    status=500,
                )
            # As perdas são zeradas SÓ AQUI: antes disto, o trabalho anterior
            # ainda pode voltar, e apagar a evidência dele deixaria um plano
            # incompleto se apresentando como completo.
            changes.esquecer_perdas()
        return routes.make_response(
            data=decisao.to_dict(), status=200 if decisao.ok else 409
        )

    @api.route("/commit_job/", methods=["POST"])
    def commit_job_handler(doc, request):
        # O relatório é lido ANTES de fechar: `commit` zera o acumulado do
        # trabalho, e ler depois devolveria um plano vazio justamente na
        # resposta que deveria carregá-lo.
        ensaio = _grupos.dry_run
        relatorio = _grupos.rehearsal() if ensaio else None
        antes = _instantaneo()
        decisao = _grupos.commit(_corpo(request).get("job_id"))
        dados = decisao.to_dict()
        erro = None
        if decisao.action == ASSIMILATE:
            erro = _fechar(assimilar=True)
        elif decisao.action == ROLLBACK:
            # Ensaio: executou de verdade e desfaz no fim.
            erro = _fechar(assimilar=False)
        if erro:
            # O trabalho volta a existir: o grupo continua aberto no Revit e
            # tentar de novo é a saída.
            _restaurar(antes)
            dados = _falhou_ao_fechar(dados, erro, decisao.action == ASSIMILATE)
            return routes.make_response(data=dados, status=500)
        if relatorio is not None and decisao.ok:
            dados["changes_report"] = relatorio
            # Passo que não entrou na soma faz o plano MENTIR por omissão: ele
            # diria "nada mudaria" sobre um trabalho que mudaria cinco paredes.
            # A resposta deixa de se apresentar como completa.
            perdidos = changes.passos_perdidos()
            if perdidos:
                dados["ok"] = False
                dados["plano_incompleto"] = perdidos
                dados["message"] = (
                    "este plano está INCOMPLETO: {} passo(s) não entraram na soma ({}). "
                    "O que está listado aconteceu, mas há mais — não aprove por ele."
                ).format(len(perdidos), ", ".join(perdidos))
                return routes.make_response(data=dados, status=409)
        return routes.make_response(data=dados, status=200 if decisao.ok else 409)

    @api.route("/abort_job/", methods=["POST"])
    def abort_job_handler(doc, request):
        antes = _instantaneo()
        decisao = _grupos.abort(_corpo(request).get("job_id"))
        erro = None
        if decisao.action == ROLLBACK:
            erro = _fechar(assimilar=False)
        if erro:
            _restaurar(antes)
            # Mesma regra do commit: dizer "descartado" quando o Revit recusou
            # desfazer é a única mentira que estas rotas não podem contar.
            dados = _falhou_ao_fechar(decisao.to_dict(), erro, False)
            return routes.make_response(data=dados, status=500)
        return routes.make_response(
            data=decisao.to_dict(), status=200 if decisao.ok else 409
        )

    # NOTHING is the fourth outcome and it is deliberate: a refusal changes no
    # group, and leaves with 409 so the agent can tell "I did nothing because
    # you asked for the wrong job" from "done". It is not imported here because
    # nothing in this file compares against it — the handlers act on the three
    # outcomes that DO something.

    logger.info("Job group routes registered successfully")
