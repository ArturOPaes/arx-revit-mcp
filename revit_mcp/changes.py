# -*- coding: UTF-8 -*-
"""
The write report — what the Revit actually changed, and what it measured.

Why this file exists
--------------------
The approval gate on the ARCHITECTUS side receives, today, "trust me": the
``changes.json`` that reaches the server is what the agent *wrote by hand* in
the workdir. Text, not observation. ``cli/src/cad_env.rs`` even says so — it
*instructs* the agent to write the file, and nothing watches the model to
check.

That mattered when the file only listed what was done. It matters far more
now: the conformity check reads ``measurements.ambientes`` and compares it
against a versioned rule set, citing article, clause and text. A wrong list
shows the wrong thing done. A wrong **measurement reproves someone's project**
while quoting the law.

So the number carries where it came from. ``medida_pela_ponte`` is the word
the server understands for "the bridge measured this in the model"; anything
the agent merely declares is ``declarada_pelo_agente`` and the server marks it
as such. This module only ever produces the first — because everything it
reports was read through the Revit API.

The shape
---------
Fixed by ``CHANGES_JSON_FORMAT`` in ``cli/src/cad_env.rs`` and by
``conformidade.Ambiente`` on the server::

    {
      "created":  ["<id>"],
      "modified": ["<id>"],
      "deleted":  ["<id>"],
      "measurements": {
        "ambientes": [
          {"id": "...", "nome": "...", "uso": "dormitorio",
           "medicoes": {"area_piso_m2": {"valor": 12.5,
                                         "bruta": "12.5 m²",
                                         "procedencia": "medida_pela_ponte"}}}
        ]
      }
    }

The four top-level keys are **always present**, empty when nothing happened: a
route that changed nothing must say so, and an absent key reads as "the route
forgot" — which is the same silence this whole file exists to remove.

No Revit imports here on purpose: this is the half that can be tested on any
machine.
"""

# The one word the server accepts for "the bridge read this from the model".
# Keep in sync with `conformidade.MedidaPelaPonte` on the server; a typo here
# is silently downgraded to "unknown" there, which is the safe side but hides
# the measurement's actual standing.
MEDIDA_PELA_PONTE = "medida_pela_ponte"


# --- units -------------------------------------------------------------
#
# The Revit API answers in INTERNAL units, which are imperial: an area comes
# back in square feet and a length in feet, whatever the project's display
# units say. In the whole fork exactly one place converts (``rooms.py``, sq ft
# → m²), which means any route that starts reporting an area without
# converting hands the conformity check a number 10.76× too small — and the
# check would then reprove a perfectly legal bedroom while quoting the
# article and the clause.
#
# The grandeza names in the contract carry their unit (``area_piso_m2``,
# ``pe_direito_m``) precisely so this cannot be argued about. Convert here.

SQ_FT_TO_M2 = 0.09290304
FT_TO_M = 0.3048


def sq_ft_to_m2(valor, casas=2):
    """Revit internal area (sq ft) → m², rounded for the report."""
    return round(float(valor) * SQ_FT_TO_M2, casas)


def ft_to_m(valor, casas=2):
    """Revit internal length (ft) → m, rounded for the report."""
    return round(float(valor) * FT_TO_M, casas)


def _as_id(value):
    """Element ids arrive as ints, ElementId wrappers or strings."""
    if value is None:
        return None
    texto = str(value).strip()
    return texto or None


class ChangeReport(object):
    """Accumulates what a write route changed, then renders the contract."""

    def __init__(self):
        self._created = []
        self._modified = []
        self._deleted = []
        self._ambientes = []

    # --- what changed ---

    def created(self, *ids):
        self._add(self._created, ids)
        return self

    def modified(self, *ids):
        self._add(self._modified, ids)
        return self

    def deleted(self, *ids):
        self._add(self._deleted, ids)
        return self

    def _add(self, destino, ids):
        for raw in _flatten(ids):
            texto = _as_id(raw)
            # Deduped, first-seen order kept: a route that touches the same
            # wall twice changed one wall, and a report saying "2 modified"
            # would inflate what the architect is asked to approve.
            if texto is not None and texto not in destino:
                destino.append(texto)

    # --- what was measured ---

    def room(self, room_id, uso, medicoes, nome=None):
        """One room, with its measurements, all stamped as bridge-measured.

        ``medicoes`` maps a grandeza (``area_piso_m2``, ``pe_direito_m``) to
        either a plain number or a dict with ``valor``/``base``/``bruta``/
        ``condicoes``.
        """
        ambiente = {"id": _as_id(room_id), "uso": uso, "medicoes": {}}
        if nome:
            ambiente["nome"] = nome
        for grandeza, medida in (medicoes or {}).items():
            ambiente["medicoes"][grandeza] = _medicao(medida)
        self._ambientes.append(ambiente)
        return self

    # --- the contract ---

    def to_dict(self):
        relatorio = {
            "created": list(self._created),
            "modified": list(self._modified),
            "deleted": list(self._deleted),
            "measurements": {},
        }
        # `ambientes` only appears when there are rooms: an empty list would
        # read as "I looked and found no rooms", which is a different claim
        # from "this route does not measure rooms".
        if self._ambientes:
            relatorio["measurements"]["ambientes"] = list(self._ambientes)
        return relatorio


def _medicao(medida):
    if isinstance(medida, dict):
        saida = dict(medida)
    else:
        saida = {"valor": medida}
    if saida.get("valor") is not None:
        saida["valor"] = float(saida["valor"])
    if saida.get("base") is not None:
        saida["base"] = float(saida["base"])
    # Always stamped, never overridable by the caller: a route in this file
    # measured through the Revit API, and letting a caller claim otherwise
    # would be the one lie this module cannot afford.
    saida["procedencia"] = MEDIDA_PELA_PONTE
    return saida


def _flatten(valores):
    for v in valores:
        if isinstance(v, (list, tuple, set)):
            for interno in _flatten(v):
                yield interno
        else:
            yield v


def empty_report():
    """The report of a route that changed nothing.

    Exists so a read-only route has something to return that is *not* an
    absent field. The gate treats a missing report as "the route did not say",
    and "did not say" is what this whole file removes.
    """
    return ChangeReport().to_dict()
