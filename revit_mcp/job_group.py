# -*- coding: UTF-8 -*-
"""
One undo for a whole job, instead of one per call.

The problem
-----------
Every route opens its own ``DB.Transaction`` and commits — twenty-eight of
them across sixteen files. If the agent makes eight calls and the sixth
fails, the first five are already in the model, and the only undo left is
ours: close the document and swap the file back. That is blunt, it loses
everything that came after, and it does not reach the document open in
memory.

``DB.TransactionGroup`` fixes exactly that: the inner transactions still
commit, and the *group* can be rolled back afterwards — a fine undo, inside
Revit, of the whole job.

The two decisions
-----------------
**Explicit routes**, not a job id smuggled into every call: the agent says
"begin", works, and says "commit" or "abort". It reads plainly in the log,
which matters when someone is trying to find out what a machine did to their
model.

**The next call decides** what happens to an abandoned group. No timer: if the
agent dies mid-job, nothing runs on its own. The *next* ``begin`` for a
different job rolls the stale one back before opening its own. The cost is
honest and written down: a model can sit with an open group until someone
calls again.

Why this file has no Revit in it
--------------------------------
What is hard here is not calling ``TransactionGroup`` — it is deciding *what*
to call when a begin arrives with a group already open, when a commit names a
job that is not the open one, or when a commit arrives with nothing open at
all. Those are the cases that lose someone's work, and they are all decidable
without Revit. This module decides; the route performs.
"""

# Effects that a RollBack does NOT undo.
#
# A dry run *executes*: the group is rolled back at the end, so nothing sticks
# **in the model**. Everything that left the model already left. Exporting a
# sheet writes a file to disk; reloading a link changes what the document
# points at on disk; anything that calls out has already called out.
#
# This list is what the rehearsal report warns about, by name. A dry run that
# reads as "nothing happened" while a PDF was written to the architect's
# desktop is the kind of quiet lie this whole file exists to avoid.
ESCAPES_ROLLBACK = {
    "export": "arquivos exportados ficam no disco",
    "import": "o que foi importado de fora já foi lido",
    "link": "vínculos recarregados apontam para o que apontam agora",
    "print": "o que foi impresso ou publicado já saiu",
    "save": "salvar grava o arquivo, e salvar não se desfaz",
}


def escapes_in(route_paths):
    """Which warnings apply to the routes a job actually called."""
    achados = []
    for caminho in route_paths or []:
        baixo = str(caminho).lower()
        for chave, aviso in sorted(ESCAPES_ROLLBACK.items()):
            if chave in baixo and aviso not in achados:
                achados.append(aviso)
    return achados


# What the route must do to the Revit TransactionGroup.
OPEN = "open"
ROLLBACK_THEN_OPEN = "rollback_then_open"
ASSIMILATE = "assimilate"
ROLLBACK = "rollback"
NOTHING = "nothing"


class Decision(object):
    """What to do, and the sentence explaining it.

    The sentence is not decoration: it goes into the response, and it is what
    an architect (or the person reading the job transcript) has to be able to
    understand when a group was discarded.
    """

    def __init__(self, action, message, ok=True, discarded_job=None):
        self.action = action
        self.message = message
        self.ok = ok
        self.discarded_job = discarded_job

    def to_dict(self):
        saida = {"action": self.action, "message": self.message, "ok": self.ok}
        if self.discarded_job is not None:
            saida["discarded_job"] = self.discarded_job
        return saida

    def __repr__(self):  # pragma: no cover - debugging aid
        return "Decision({!r}, {!r}, ok={!r})".format(self.action, self.message, self.ok)


class JobGroups(object):
    """Which job owns the open group, if any."""

    def __init__(self):
        self._open_job = None
        self._dry_run = False
        self._reports = []
        self._routes = []

    @property
    def open_job(self):
        return self._open_job

    @property
    def dry_run(self):
        return self._dry_run

    def record(self, changes_report, route=None):
        """A write route ran; keep what it changed, and where.

        Kept even outside a job: a route that ran with no job open still
        changed the model, and dropping the record would make the transcript
        quieter than the truth.
        """
        if changes_report:
            self._reports.append(changes_report)
        if route:
            self._routes.append(str(route))

    def rehearsal(self):
        """The accumulated report of the job, plus what a rollback will not undo."""
        somado = _merge(self._reports)
        avisos = escapes_in(self._routes)
        if avisos:
            # Nomeados, não contados: "3 efeitos não revertidos" não diz à
            # pessoa o que procurar no computador dela.
            somado["not_undone"] = avisos
        return somado

    def begin(self, job_id, dry_run=False):
        job_id = _clean(job_id)
        if not job_id:
            # A group with no name cannot be committed or aborted by name
            # later — it would only ever be closed by accident.
            return Decision(NOTHING, "begin needs a job id", ok=False)

        if self._open_job == job_id:
            # A retried begin is not a new job. Discarding here would throw
            # away work the agent had already done, because its previous
            # answer got lost on the way back.
            return Decision(NOTHING, "job {} is already open".format(job_id))

        if self._open_job is not None:
            anterior = self._open_job
            self._reiniciar(job_id, dry_run)
            return Decision(
                ROLLBACK_THEN_OPEN,
                "job {} was left open and is being discarded so job {} can start".format(
                    anterior, job_id
                ),
                discarded_job=anterior,
            )

        self._reiniciar(job_id, dry_run)
        return Decision(
            OPEN,
            "job {} started{}".format(job_id, " as a rehearsal" if dry_run else ""),
        )

    def _reiniciar(self, job_id, dry_run):
        self._open_job = job_id
        self._dry_run = bool(dry_run)
        # O acumulado é POR TRABALHO: carregar o do anterior faria o plano de
        # aprovação de um job mostrar o que outro teria mudado.
        self._reports = []
        self._routes = []

    def commit(self, job_id):
        job_id = _clean(job_id)
        if self._open_job is None:
            # NOT a quiet success: the gate would read "committed" and believe
            # a group had wrapped the work, when nothing did.
            return Decision(NOTHING, "no job is open to commit", ok=False)
        if self._open_job != job_id:
            # Committing someone else's group would make the wrong job's work
            # permanent under this job's name.
            return Decision(
                NOTHING,
                "job {} is open, not {}".format(self._open_job, job_id),
                ok=False,
            )
        ensaio = self._dry_run
        self._open_job = None
        self._dry_run = False
        if ensaio:
            # O ENSAIO desfaz no fim — é o que o torna ensaio. E devolve o
            # relatório do que TERIA mudado, que é o plano de aprovação
            # deixando de ser prosa do agente para ser observação.
            return Decision(
                ROLLBACK, "rehearsal of job {} undone; nothing persisted".format(job_id)
            )
        return Decision(ASSIMILATE, "job {} committed".format(job_id))

    def abort(self, job_id):
        job_id = _clean(job_id)
        if self._open_job is None:
            return Decision(NOTHING, "no job is open to abort", ok=False)
        if self._open_job != job_id:
            return Decision(
                NOTHING,
                "job {} is open, not {}".format(self._open_job, job_id),
                ok=False,
            )
        self._open_job = None
        self._dry_run = False
        return Decision(ROLLBACK, "job {} discarded".format(job_id))

    def forget(self):
        """The group is gone for a reason outside our reach — Revit closed,
        the document was shut. Forgetting is not a rollback: whatever the
        group held is already decided by Revit, and pretending otherwise
        would make the next begin roll back a group that no longer exists."""
        anterior = self._open_job
        self._open_job = None
        self._dry_run = False
        return anterior


def _clean(job_id):
    return None if job_id is None else str(job_id).strip() or None


def _merge(reports):
    """Soma os relatórios das chamadas num só, do jeito que o contrato pede."""
    somado = {"created": [], "modified": [], "deleted": [], "measurements": {}}
    ambientes = []
    for r in reports:
        for chave in ("created", "modified", "deleted"):
            for item in r.get(chave) or []:
                # Deduplicado ENTRE chamadas também: o agente que cria e depois
                # modifica a mesma parede mexeu numa parede, e um plano que
                # diga "2" pede aprovação sobre um estrago maior do que o real.
                if item not in somado[chave]:
                    somado[chave].append(item)
        ambientes.extend((r.get("measurements") or {}).get("ambientes") or [])
    if ambientes:
        somado["measurements"]["ambientes"] = ambientes
    return somado
