# -*- coding: UTF-8 -*-
"""
O relatório de escrita: o que o Revit de fato mudou, e o que ele mediu.

O gate de aprovação recebe hoje "confie em mim" — o `changes.json` que chega
ao servidor é o que o agente ESCREVEU à mão no workdir. Texto, não observação.

Isso já era ruim quando o arquivo só listava o que foi feito. Ficou pior
depois que a conferência de norma passou a ler `measurements.ambientes` e
cruzar contra a régua versionada: **lista errada mostra o que o agente fez; a
medição errada reprova o projeto de alguém**, citando artigo e trecho.

O que estes testes trancam é a forma do contrato e a procedência do número.
O que eles NÃO provam: que o Revit devolveu aquele número. Isso só numa
máquina com Revit.
"""

import pytest

from revit_mcp.changes import MEDIDA_PELA_PONTE, ChangeReport, empty_report


class TestOContrato:
    def test_as_quatro_chaves_existem_mesmo_sem_nada_ter_mudado(self):
        # Chave ausente lê-se como "a rota esqueceu"; lista vazia diz "não
        # mudei nada". São afirmações diferentes, e o gate trata as duas de
        # jeito diferente.
        r = empty_report()
        assert r == {"created": [], "modified": [], "deleted": [], "measurements": {}}

    def test_uma_rota_que_so_le_devolve_o_mesmo_que_empty(self):
        assert ChangeReport().to_dict() == empty_report()

    def test_ambientes_so_aparece_quando_ha_ambiente(self):
        # Lista vazia aqui leria como "procurei ambientes e não achei", que é
        # outra afirmação — e a conferência de norma trata "não achei" como
        # lacuna.
        assert "ambientes" not in ChangeReport().to_dict()["measurements"]
        r = ChangeReport().room("r1", "dormitorio", {"area_piso_m2": 12.0})
        assert len(r.to_dict()["measurements"]["ambientes"]) == 1


class TestOsIdentificadores:
    def test_aceita_numero_texto_e_lista(self):
        r = ChangeReport().created(101, "102", [103, 104]).to_dict()
        assert r["created"] == ["101", "102", "103", "104"]

    def test_o_mesmo_elemento_duas_vezes_conta_UMA(self):
        # Uma rota que toca a mesma parede duas vezes mudou uma parede. Contar
        # duas infla o que o arquiteto está sendo convidado a aprovar.
        r = ChangeReport().modified(7, 7, "7").to_dict()
        assert r["modified"] == ["7"]

    def test_a_ordem_de_chegada_e_preservada(self):
        r = ChangeReport().created(3, 1, 2).to_dict()
        assert r["created"] == ["3", "1", "2"]

    @pytest.mark.parametrize("vazio", [None, "", "   "])
    def test_identificador_vazio_nao_entra(self, vazio):
        # Um id em branco no relatório vira uma linha "elemento" sem elemento
        # na tela de aprovação.
        assert ChangeReport().created(vazio).to_dict()["created"] == []

    def test_as_tres_listas_sao_independentes(self):
        r = ChangeReport().created(1).modified(2).deleted(3).to_dict()
        assert (r["created"], r["modified"], r["deleted"]) == (["1"], ["2"], ["3"])


class TestAProcedencia:
    def test_toda_medicao_sai_marcada_como_MEDIDA_pela_ponte(self):
        # É a razão de existir deste módulo: o servidor precisa distinguir um
        # número lido do modelo de um número que o agente declarou.
        r = ChangeReport().room("r1", "dormitorio", {"area_piso_m2": 12.5}).to_dict()
        medicao = r["measurements"]["ambientes"][0]["medicoes"]["area_piso_m2"]
        assert medicao["procedencia"] == MEDIDA_PELA_PONTE

    def test_quem_chama_NAO_consegue_dizer_que_o_numero_e_de_outra_origem(self):
        # Deixar a procedência ser passada de fora abriria a única mentira que
        # este módulo não pode contar: número declarado se passando por medido.
        r = ChangeReport().room(
            "r1", "dormitorio", {"area_piso_m2": {"valor": 12.5, "procedencia": "declarada_pelo_agente"}}
        ).to_dict()
        medicao = r["measurements"]["ambientes"][0]["medicoes"]["area_piso_m2"]
        assert medicao["procedencia"] == MEDIDA_PELA_PONTE

    def test_a_palavra_e_exatamente_a_que_o_servidor_conhece(self):
        # Uma variação ("medida-pela-ponte", "ponte") o servidor normaliza
        # para desconhecida — o lado seguro, e que esconde que a medição de
        # fato veio do modelo.
        assert MEDIDA_PELA_PONTE == "medida_pela_ponte"


class TestAsMedicoes:
    def test_numero_solto_vira_medicao_com_valor(self):
        r = ChangeReport().room("r1", "dormitorio", {"pe_direito_m": 2.7}).to_dict()
        assert r["measurements"]["ambientes"][0]["medicoes"]["pe_direito_m"]["valor"] == 2.7

    def test_regra_fracionaria_leva_numerador_e_base(self):
        # Iluminação é abertura sobre piso: sem a base, o servidor não tem o
        # que dividir e a regra sai como não medida.
        r = ChangeReport().room(
            "r1", "dormitorio", {"iluminacao": {"valor": 1.5, "base": 12.0, "bruta": "1.5 m² / 12 m²"}}
        ).to_dict()
        m = r["measurements"]["ambientes"][0]["medicoes"]["iluminacao"]
        assert (m["valor"], m["base"], m["bruta"]) == (1.5, 12.0, "1.5 m² / 12 m²")

    def test_os_numeros_saem_como_float_mesmo_vindo_inteiros(self):
        r = ChangeReport().room("r1", "sala", {"area_piso_m2": 12}).to_dict()
        assert isinstance(r["measurements"]["ambientes"][0]["medicoes"]["area_piso_m2"]["valor"], float)

    def test_as_condicoes_declaradas_atravessam(self):
        # `abertura_zenital` é o que autoriza a régua a abater — some ela e a
        # sala passa a reprovar por uma regra que não se aplicava.
        r = ChangeReport().room(
            "r1", "dormitorio", {"iluminacao": {"valor": 1.0, "base": 12.0, "condicoes": ["abertura_zenital"]}}
        ).to_dict()
        m = r["measurements"]["ambientes"][0]["medicoes"]["iluminacao"]
        assert m["condicoes"] == ["abertura_zenital"]

    def test_o_nome_do_ambiente_e_opcional_e_o_uso_nao(self):
        # O uso é o que casa o ambiente com a regra; sem ele a conferência não
        # tem como classificar e sai como lacuna.
        r = ChangeReport().room("r1", "dormitorio", {}).to_dict()
        ambiente = r["measurements"]["ambientes"][0]
        assert ambiente["uso"] == "dormitorio"
        assert "nome" not in ambiente

        com_nome = ChangeReport().room("r1", "dormitorio", {}, nome="Suíte").to_dict()
        assert com_nome["measurements"]["ambientes"][0]["nome"] == "Suíte"

    def test_dois_ambientes_saem_na_ordem_em_que_foram_medidos(self):
        r = ChangeReport().room("b", "sala", {}).room("a", "dormitorio", {}).to_dict()
        assert [x["id"] for x in r["measurements"]["ambientes"]] == ["b", "a"]


class TestUnidades:
    """A API do Revit responde em unidade INTERNA, que é imperial.

    No fork inteiro existe UM lugar que converte. Qualquer rota que passe a
    reportar área sem converter entrega à conferência de norma um número 10,76
    vezes menor — e a régua reprovaria um dormitório perfeitamente legal
    citando o artigo e o trecho.
    """

    def test_area_de_pe_quadrado_para_metro_quadrado(self):
        from revit_mcp.changes import sq_ft_to_m2

        # 100 pés² são pouco mais de 9 m². Um dormitório de 9 m² reportado
        # como "100" passaria por enorme; reportado como 9,29 é o que ele é.
        assert sq_ft_to_m2(100) == 9.29

    def test_comprimento_de_pe_para_metro(self):
        from revit_mcp.changes import ft_to_m

        # 8 pés é o pé-direito americano padrão: 2,44 m — abaixo do mínimo
        # brasileiro de 2,50 na maioria dos municípios. Reportar "8" faria a
        # régua achar que sobra folga de cinco metros.
        assert ft_to_m(8) == 2.44

    def test_a_conversao_e_a_exata_e_nao_a_arredondada(self):
        from revit_mcp.changes import FT_TO_M, SQ_FT_TO_M2

        # 0.092903 (seis casas) acumula erro em áreas grandes; o fator exato
        # do pé internacional é 0.3048 ao quadrado.
        assert SQ_FT_TO_M2 == FT_TO_M**2

    def test_zero_continua_zero(self):
        from revit_mcp.changes import ft_to_m, sq_ft_to_m2

        assert sq_ft_to_m2(0) == 0.0
        assert ft_to_m(0) == 0.0

    def test_da_para_pedir_mais_casas_quando_a_regra_e_fracionaria(self):
        from revit_mcp.changes import sq_ft_to_m2

        # A regra de iluminação divide abertura por piso; arredondar os dois
        # a duas casas antes de dividir move a fração.
        assert sq_ft_to_m2(100, casas=4) == 9.2903
