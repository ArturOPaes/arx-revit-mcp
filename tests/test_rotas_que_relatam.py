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
# Medido em 28/08/2026, e REMEDIDO no mesmo dia depois que um revisor mostrou
# que o inventário subcontava: eu procurava `Transaction(` no trecho do
# handler, e isso perdia transação aberta em ajudante e rota que muda disco sem
# transação nenhuma. Eram 18; são 22.
#
# Encolher esta lista é o trabalho; deixá-la crescer é o defeito. E ela não é
# permissão: `/execute_code/` roda código arbitrário dentro de transação, e
# `/export_document/`, `/export_ifc/` e `/link_file/` escapam do rollback sem
# nem aparecer no aviso, porque a rota nunca é registrada.
SEM_RELATORIO = {
    "/clear_colors/",
    "/color_splash/",
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
    "/load_family/",
    "/place_family/",
    "/save_document/",
    "/set_parameter/",
    "/tag_walls/",
    "/transform_elements/",
}


# Escrita que NÃO abre transação, e por isso escapava do inventário.
#
# Um revisor mediu o buraco: eu procurava `Transaction(` dentro do trecho da
# rota, e isso perde três coisas — transação aberta num AJUDANTE (fora do
# trecho), e rota que muda disco ou modelo sem transação nenhuma. Contar 26
# quando são pelo menos 30 fazia a dívida parecer menor do que é.
MUTAM_SEM_TRANSACAO = {
    "/save_document/",   # grava o arquivo; salvar não se desfaz
    "/load_family/",     # traz família para o modelo
}

# Rotas cuja transação vive num ajudante, fora do trecho do handler.
TRANSACAO_EM_AJUDANTE = {
    "/color_splash/",
    "/clear_colors/",
}


def inventario():
    """(caminho, escreve, relata) para cada rota do fork.

    "Escreve" é mais largo que "abre transação no próprio handler" — foi
    exatamente essa estreiteza que um revisor mediu, e ela fazia a lista de
    dívida parecer menor do que é.
    """
    achadas = []
    for arquivo in sorted((RAIZ / "revit_mcp").glob("*.py")):
        texto = arquivo.read_text(encoding="utf-8")
        marcas = list(re.finditer(r'@api\.route\("([^"]+)"(?:,\s*methods=(\[[^\]]*\]))?\)', texto))
        for i, m in enumerate(marcas):
            fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
            corpo = texto[m.end() : fim]
            caminho = m.group(1)
            escreve = (
                "Transaction(" in corpo
                or caminho in MUTAM_SEM_TRANSACAO
                or caminho in TRANSACAO_EM_AJUDANTE
            )
            achadas.append((caminho, escreve, "changes_report" in corpo))
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


# Verbos da API do Revit que MUDAM alguma coisa — modelo ou disco.
#
# Esta é a fonte INDEPENDENTE das listas escritas à mão. Um revisor mostrou
# que o teste anterior provava a lista com a própria lista: o detector marcava
# como escrita qualquer rota que estivesse no conjunto manual, e o teste
# conferia que as rotas do conjunto manual estavam marcadas. Tirar uma rota
# dos dois lugares ao mesmo tempo passava verde — foi o que ele fez com
# `/load_family/`, que executa `doc.LoadFamily(...)`.
#
# Procurar o VERBO no corpo da rota não depende de nenhuma lista.
VERBOS_QUE_MUDAM = (
    "Transaction(",
    "doc.Delete(",
    "doc.Create",
    "doc.LoadFamily(",
    ".Save(",
    ".SaveAs(",
    "ActivateView(",
    "Duplicate(",
)


def test_nenhuma_rota_com_verbo_de_MUDANCA_fica_fora_do_inventario():
    """A fonte independente: o verbo, não a lista.

    Se uma rota chama `doc.LoadFamily` ou `Transaction(` e não aparece como
    escrita, a lista manual envelheceu — e é assim que uma rota nova entra sem
    relatório e sem ninguém ver.
    """
    escrevem = {c for c, escreve, _ in inventario() if escreve}
    faltando = []
    for arquivo in sorted((RAIZ / "revit_mcp").glob("*.py")):
        texto = arquivo.read_text(encoding="utf-8")
        marcas = list(re.finditer(r'@api\.route\("([^"]+)"', texto))
        for i, m in enumerate(marcas):
            fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
            corpo = texto[m.end() : fim]
            caminho = m.group(1)
            if any(v in corpo for v in VERBOS_QUE_MUDAM) and caminho not in escrevem:
                faltando.append(caminho)

    assert not faltando, (
        "estas rotas chamam um verbo que muda o modelo ou o disco e não estão "
        "classificadas como escrita: {}. A lista manual envelheceu."
    ).format(sorted(set(faltando)))


def test_a_fonte_independente_encontra_alguma_coisa():
    # Um detector que não casa com nada passa sempre e não defende nada.
    achou = 0
    for arquivo in sorted((RAIZ / "revit_mcp").glob("*.py")):
        texto = arquivo.read_text(encoding="utf-8")
        achou += sum(texto.count(v) for v in VERBOS_QUE_MUDAM)
    assert achou > 20, f"os verbos de mudança quase não aparecem no código ({achou})"


def test_o_inventario_enxerga_escrita_que_nao_abre_transacao():
    """A estreiteza que um revisor mediu.

    Procurar `Transaction(` dentro do trecho do handler perde três coisas:
    transação aberta num ajudante, rota que grava em disco, e rota que traz
    coisa para o modelo sem transação. Contar 26 quando são 30 fazia a dívida
    parecer menor do que é — e uma dívida subcontada é pior que uma dívida
    grande, porque ninguém sabe o tamanho do buraco.
    """
    escrevem = {c for c, escreve, _ in inventario() if escreve}
    for caminho in MUTAM_SEM_TRANSACAO | TRANSACAO_EM_AJUDANTE:
        assert caminho in escrevem, f"{caminho} muda o modelo e sumiu do inventário"


@pytest.mark.parametrize("caminho", sorted(SEM_RELATORIO))
def test_cada_divida_e_de_uma_rota_que_existe(caminho):
    # Dívida sobre rota que não existe mais é ruído que ninguém remove.
    todas = {c for c, _, _ in inventario()}
    assert caminho in todas, f"{caminho} está na lista de dívida e não existe mais no código"
