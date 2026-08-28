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

from .job_group import (
    ASSIMILATE,
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


def _corpo(request):
    try:
        dados = request.data
        if isinstance(dados, str):
            dados = json.loads(dados)
        return dados or {}
    except Exception:
        return {}


def _abrir(doc, job_id):
    global _grupo_aberto
    _grupo_aberto = DB.TransactionGroup(doc, "PlanArchi job {}".format(job_id))
    _grupo_aberto.Start()


def _fechar(assimilar):
    """Assimilate or roll back, and forget either way.

    Forgetting even when the Revit call raises is deliberate: a group we can
    no longer act on must not stay recorded as open, or the next begin would
    try to roll back something that is not there.
    """
    global _grupo_aberto
    grupo, _grupo_aberto = _grupo_aberto, None
    if grupo is None:
        return
    try:
        if assimilar:
            grupo.Assimilate()
        else:
            grupo.RollBack()
    except Exception as e:  # pragma: no cover - needs Revit
        logger.warning("job group could not be closed: %s", e)


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
        decisao = _grupos.begin(job_id, dry_run=bool(corpo.get("dry_run")))
        if decisao.action == ROLLBACK_THEN_OPEN:
            _fechar(assimilar=False)
            _abrir(doc, job_id)
        elif decisao.action == OPEN:
            _abrir(doc, job_id)
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
        decisao = _grupos.commit(_corpo(request).get("job_id"))
        if decisao.action == ASSIMILATE:
            _fechar(assimilar=True)
        elif decisao.action == ROLLBACK:
            # Ensaio: executou de verdade e desfaz no fim.
            _fechar(assimilar=False)
        dados = decisao.to_dict()
        if relatorio is not None and decisao.ok:
            dados["changes_report"] = relatorio
        return routes.make_response(data=dados, status=200 if decisao.ok else 409)

    @api.route("/abort_job/", methods=["POST"])
    def abort_job_handler(doc, request):
        decisao = _grupos.abort(_corpo(request).get("job_id"))
        if decisao.action == ROLLBACK:
            _fechar(assimilar=False)
        return routes.make_response(
            data=decisao.to_dict(), status=200 if decisao.ok else 409
        )

    # NOTHING is the fourth outcome and it is deliberate: a refusal changes no
    # group, and leaves with 409 so the agent can tell "I did nothing because
    # you asked for the wrong job" from "done". It is not imported here because
    # nothing in this file compares against it — the handlers act on the three
    # outcomes that DO something.

    logger.info("Job group routes registered successfully")
