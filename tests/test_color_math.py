# -*- coding: UTF-8 -*-
"""
A primeira lógica de ``revit_mcp/`` com rede de teste.

Os dezenove módulos importam ``pyrevit``, ``Autodesk`` ou ``System`` no topo —
CLR, que só existe dentro do Revit —, então nenhum deles podia sequer ser
IMPORTADO nesta máquina. Stubar o .NET seria uma ficção grande, do tipo que dá
confiança falsa.

O caminho honesto é o outro: separar a aritmética, que nunca precisou do Revit,
do embrulho em ``DB.Color``, que precisa. Isto cobre a primeira metade, e
prova o padrão para os próximos módulos.

O que estes testes NÃO provam: que o Revit aceita a cor, que a transação
commita, que o elemento muda na tela. Isso só numa máquina com Revit.
"""

import math

import pytest

from revit_mcp.color_math import (
    BASE_COLORS,
    distinct_rgb,
    gradient_rgb,
    hex_to_rgb,
    interpolate_rgb,
    safe_float,
)


class TestCoresDistintas:
    def test_nenhuma_cor_quando_nao_ha_o_que_colorir(self):
        assert distinct_rgb(0) == []

    def test_as_primeiras_saem_da_lista_base_na_ordem(self):
        assert distinct_rgb(3) == BASE_COLORS[:3]

    def test_passando_da_lista_base_a_cor_repete_MAIS_ESCURA(self):
        # Sem o escurecimento, a 26ª categoria receberia exatamente o mesmo
        # vermelho da 1ª, e a legenda passaria a mentir sem sintoma nenhum.
        cores = distinct_rgb(len(BASE_COLORS) + 1)
        primeira, repetida = cores[0], cores[-1]
        assert repetida != primeira
        assert all(r <= p for r, p in zip(repetida, primeira))

    def test_nunca_escurece_ate_o_preto(self):
        # Escurecer sem piso levaria as cores a (0,0,0) — todas iguais, e
        # invisíveis sobre fundo escuro.
        cores = distinct_rgb(len(BASE_COLORS) * 12)
        assert all(any(c > 0 for c in cor) for cor in cores)

    def test_cada_cor_e_um_trio_valido(self):
        for cor in distinct_rgb(60):
            assert len(cor) == 3
            assert all(isinstance(c, int) and 0 <= c <= 255 for c in cor)


class TestGradiente:
    def test_um_passo_so_e_a_ponta_QUENTE(self):
        # A ponta fria num gradiente de um elemento leria como "não há nada
        # aqui" — e há: há um valor, no topo da escala.
        assert gradient_rgb(1) == [(255, 0, 0)]

    def test_zero_tambem_devolve_uma_cor_em_vez_de_lista_vazia(self):
        assert gradient_rgb(0) == [(255, 0, 0)]

    def test_vai_de_azul_a_vermelho_e_inclui_as_duas_pontas(self):
        cores = gradient_rgb(5)
        assert len(cores) == 5
        assert cores[0] == (0, 0, 255)
        assert cores[-1] == (255, 0, 0)

    def test_o_vermelho_cresce_e_o_azul_cai_sem_voltar_atras(self):
        cores = gradient_rgb(9)
        vermelhos = [c[0] for c in cores]
        azuis = [c[2] for c in cores]
        assert vermelhos == sorted(vermelhos)
        assert azuis == sorted(azuis, reverse=True)

    def test_o_verde_pica_no_meio(self):
        cores = gradient_rgb(9)
        verdes = [c[1] for c in cores]
        assert verdes.index(max(verdes)) == 4


class TestInterpolar:
    @pytest.mark.parametrize(
        "posicao,esperado",
        [(0.0, (0, 0, 255)), (0.5, (127, 255, 127)), (1.0, (255, 0, 0))],
    )
    def test_as_tres_posicoes_de_referencia(self, posicao, esperado):
        assert interpolate_rgb(posicao) == esperado

    @pytest.mark.parametrize("fora", [-5.0, -0.0001, 1.0001, 42.0, math.inf])
    def test_posicao_fora_da_faixa_e_APARADA_em_vez_de_estourar(self, fora):
        # Um valor fora da faixa vem de divisão por intervalo zero — todos os
        # elementos com o mesmo valor de parâmetro. Estourar ali mataria a
        # coloração inteira por causa de um caso comum.
        cor = interpolate_rgb(fora)
        assert all(0 <= c <= 255 for c in cor)


class TestHexParaRgb:
    @pytest.mark.parametrize("texto", ["#FF0000", "FF0000", "ff0000"])
    def test_aceita_com_e_sem_cerquilha_e_em_qualquer_caixa(self, texto):
        assert hex_to_rgb(texto) == (255, 0, 0)

    def test_le_a_cor_certa(self):
        assert hex_to_rgb("#3399CC") == (51, 153, 204)

    @pytest.mark.parametrize("ruim", ["", "#GGG", "xyz", "#12", None, 42])
    def test_texto_impossivel_cai_no_padrao_em_vez_de_estourar(self, ruim):
        # Isto vem de entrada de usuário. Estourar aqui derrubaria um trabalho
        # que já tinha colorido metade dos elementos.
        assert hex_to_rgb(ruim) == (255, 0, 0)

    def test_o_padrao_e_escolhivel(self):
        assert hex_to_rgb("nada", fallback=(1, 2, 3)) == (1, 2, 3)


class TestValorParaOrdenar:
    @pytest.mark.parametrize("texto,valor", [("3.5", 3.5), ("-2", -2.0), ("+7", 7.0)])
    def test_numero_puro(self, texto, valor):
        assert safe_float(texto) == valor

    @pytest.mark.parametrize("texto,valor", [("3.5 m", 3.5), ("120mm", 120.0)])
    def test_corta_o_sufixo_de_unidade(self, texto, valor):
        assert safe_float(texto) == valor

    @pytest.mark.parametrize("texto,valor", [("15 m²", 15.0), ("2.5 m³", 2.5)])
    def test_area_e_volume_ordenam_pelo_NUMERO(self, texto, valor):
        # Este teste nasceu vermelho, e o defeito era do upstream: em Python 3
        # `"²".isdigit()` é True, então a varredura parava no ² de "15 m²",
        # não cortava nada, não convertia, e devolvia `inf`.
        #
        # O efeito: área de ambiente escrita na unidade que o arquiteto de
        # fato usa ordenava como se nunca tivesse sido medida — no fim da
        # lista, junto com os vazios. `isdecimal` não confunde expoente com
        # dígito.
        assert safe_float(texto) == valor

    @pytest.mark.parametrize("vazio", ["", None, "None"])
    def test_ausente_vai_para_o_FIM_e_nao_para_o_comeco(self, vazio):
        # `inf`, e não 0: com zero, um parâmetro em branco apareceria como o
        # MENOR valor da lista, e uma sala sem área medida encabeçaria o
        # ranking das menores salas.
        assert safe_float(vazio) == float("inf")

    @pytest.mark.parametrize("ruim", ["abc", "m²", "--", "."])
    def test_o_que_nao_e_numero_tambem_vai_para_o_fim(self, ruim):
        assert safe_float(ruim) == float("inf")

    def test_ordenar_uma_lista_mista_nao_estoura_e_poe_os_vazios_no_fim(self):
        bruto = ["12 m", "", "3.5 m", "abc", "120mm"]
        assert sorted(bruto, key=safe_float) == ["3.5 m", "12 m", "120mm", "", "abc"]
