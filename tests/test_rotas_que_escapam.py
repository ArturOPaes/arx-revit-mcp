# -*- coding: utf-8 -*-
"""
Quais rotas o aviso "isto não se desfaz" acusa — hoje, e da próxima vez.

O ensaio executa de verdade e desfaz no fim. O RollBack alcança o modelo, não
o mundo: arquivo exportado fica no disco, vínculo recarregado aponta para onde
aponta agora, salvar não se desfaz. `escapes_in` avisa sobre isso, casando
PEDAÇO DE TEXTO no caminho da rota.

Casar por pedaço é barato e tem um jeito de envelhecer mal nos dois sentidos:

- uma rota nova de LEITURA com "link" no nome (`/get_element_links/`) passaria
  a ser acusada, e um aviso que aparece sem motivo é um aviso que a pessoa
  aprende a pular — justo o campo que conta que um PDF foi escrito na área de
  trabalho dela;
- uma rota nova que EXPORTA com outro nome (`/dump_sheets/`) passaria em
  branco, e aí o ensaio se apresenta como "nada aconteceu" enquanto aconteceu.

Este teste não decide qual dos dois; ele impede que qualquer um aconteça sem
alguém olhar.
"""

import re
from pathlib import Path

from revit_mcp.job_group import escapes_in

RAIZ = Path(__file__).resolve().parent.parent

# Conferido à mão em 28/08/2026 contra as 50 rotas do fork. Mexer nesta lista é
# uma decisão: ou uma rota nova de fato escapa do RollBack, e entra, ou ela foi
# acusada por acidente do casamento por pedaço, e o casamento é que precisa
# mudar.
ACUSADAS_HOJE = {
    "/export_document/",
    "/export_ifc/",
    "/link_file/",
    "/save_document/",
}


def rotas_do_fork():
    achadas = set()
    for arquivo in (RAIZ / "revit_mcp").glob("*.py"):
        achadas.update(re.findall(r'@api\.route\("([^"]+)"', arquivo.read_text(encoding="utf-8")))
    return achadas


def test_ha_rotas_para_conferir():
    # Um teste que roda sobre lista vazia passa e não defende nada.
    assert len(rotas_do_fork()) > 20


def test_o_aviso_acusa_exatamente_as_rotas_conhecidas():
    acusadas = {r for r in rotas_do_fork() if escapes_in([r])}
    assert acusadas == ACUSADAS_HOJE, (
        "mudou quem o aviso acusa. Se a rota nova de fato escapa do RollBack, "
        "acrescente-a a ACUSADAS_HOJE; se foi acusada por acidente do "
        "casamento por pedaço de texto, conserte o casamento — um aviso que "
        "aparece sem motivo é um aviso que a pessoa aprende a pular."
    )


def test_toda_rota_acusada_tem_uma_frase_dizendo_o_que_fica():
    # "Isto não se desfaz" sem dizer o quê manda a pessoa procurar no escuro.
    for rota in ACUSADAS_HOJE:
        avisos = escapes_in([rota])
        assert avisos, rota
        for aviso in avisos:
            assert len(aviso) > 20, f"{rota}: aviso curto demais para dizer algo — {aviso}"
