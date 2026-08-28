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

    @property
    def open_job(self):
        return self._open_job

    def begin(self, job_id):
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
            self._open_job = job_id
            return Decision(
                ROLLBACK_THEN_OPEN,
                "job {} was left open and is being discarded so job {} can start".format(
                    anterior, job_id
                ),
                discarded_job=anterior,
            )

        self._open_job = job_id
        return Decision(OPEN, "job {} started".format(job_id))

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
        self._open_job = None
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
        return Decision(ROLLBACK, "job {} discarded".format(job_id))

    def forget(self):
        """The group is gone for a reason outside our reach — Revit closed,
        the document was shut. Forgetting is not a rollback: whatever the
        group held is already decided by Revit, and pretending otherwise
        would make the next begin roll back a group that no longer exists."""
        anterior = self._open_job
        self._open_job = None
        return anterior


def _clean(job_id):
    return None if job_id is None else str(job_id).strip() or None
