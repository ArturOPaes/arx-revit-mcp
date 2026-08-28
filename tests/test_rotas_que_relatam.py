# -*- coding: utf-8 -*-
"""
Quantas rotas de escrita devolvem o relatório — medido, não afirmado.

O README dizia *"Every route that changes the model returns a
`changes_report`"*. Era falso: das 26 rotas que abrem transação, oito
devolviam. Um revisor mediu e apontou, e a frase é do tipo mais caro — quem a
lê para de conferir.

Este teste faz o inventário a partir do CÓDIGO e prende o estado atual. Ele
não exige que todas relatem: exige que a lista das que **não** relatam seja
conhecida, e que ela não cresça sem alguém decidir.

Uma rota nova que escreve e não relata some do plano de aprovação: num ensaio,
o que ela mudaria soma zero, e o arquiteto aprova um plano que não menciona o
que vai acontecer.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

# Rotas que ABREM TRANSAÇÃO e ainda não devolvem `changes_report`.
# Medido em 28/08/2026. Encolher esta lista é o trabalho; deixá-la crescer é o
# defeito.
SEM_RELATORIO = {
    "/create_detail_line/",
    "/create_framing/",
    "/create_grid/",
    "/create_level/",
    "/create_line/",
    "/create_mep_system/",
    "/create_schedule/",
    "/create_sheet/",
    "/create_surface/",
    "/create_view/",
    "/execute_code/",
    "/export_document/",
    "/export_ifc/",
    "/link_file/",
    "/place_family/",
    "/set_parameter/",
    "/tag_walls/",
    "/transform_elements/",
}


def inventario():
    """(caminho, escreve, relata) para cada rota do fork."""
    achadas = []
    for arquivo in sorted((RAIZ / "revit_mcp").glob("*.py")):
        texto = arquivo.read_text(encoding="utf-8")
        marcas = list(re.finditer(r'@api\.route\("([^"]+)"(?:,\s*methods=(\[[^\]]*\]))?\)', texto))
        for i, m in enumerate(marcas):
            fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
            corpo = texto[m.end() : fim]
            achadas.append(
                (
                    m.group(1),
                    "Transaction(" in corpo,
                    "changes_report" in corpo,
                )
            )
    return achadas


def test_o_inventario_nao_sai_vazio():
    # Um guarda que roda sobre lista vazia passa e não defende nada.
    assert len(inventario()) > 40


def test_a_lista_das_que_nao_relatam_e_exatamente_a_conhecida():
    escrevem_sem_relatar = {c for c, escreve, relata in inventario() if escreve and not relata}
    novas = escrevem_sem_relatar - SEM_RELATORIO
    resolvidas = SEM_RELATORIO - escrevem_sem_relatar

    assert not novas, (
        "rota que escreve no modelo e não devolve relatório: {}. Num ensaio ela "
        "soma zero, e o arquiteto aprova um plano que não menciona o que vai "
        "acontecer. Ligue o relatório, ou acrescente-a a SEM_RELATORIO com o "
        "motivo — mas saiba que a lista é dívida, não permissão."
    ).format(sorted(novas))

    assert not resolvidas, (
        "estas passaram a relatar e continuam listadas como dívida: {}. "
        "Tire-as de SEM_RELATORIO — lista de dívida que não encolhe deixa de "
        "ser lida."
    ).format(sorted(resolvidas))


def test_pelo_menos_as_instrumentadas_continuam_relatando():
    # As oito que já relatam são o piso: perder qualquer uma é regressão.
    relatam = {c for c, escreve, relata in inventario() if escreve and relata}
    assert len(relatam) >= 8, f"o número de rotas que relatam caiu para {len(relatam)}: {sorted(relatam)}"


@pytest.mark.parametrize("caminho", sorted(SEM_RELATORIO))
def test_cada_divida_e_de_uma_rota_que_existe(caminho):
    # Dívida sobre rota que não existe mais é ruído que ninguém remove.
    todas = {c for c, _, _ in inventario()}
    assert caminho in todas, f"{caminho} está na lista de dívida e não existe mais no código"
