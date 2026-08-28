# -*- coding: UTF-8 -*-
"""
Um desfazer para o trabalho inteiro, em vez de um por chamada.

Hoje cada rota abre a própria transação e comita — vinte e oito delas em
dezesseis arquivos. Se o agente faz oito chamadas e a sexta falha, as cinco
primeiras já estão no modelo, e o único desfazer é o nosso: fechar o documento
e trocar o arquivo. Bruto, leva junto tudo que veio depois, e não alcança o
documento aberto em memória.

Duas decisões do Artur moldam o que está aqui:

- **rotas explícitas** de começar e fechar, em vez do número do trabalho
  viajando em cada chamada — lê-se no registro, e é isso que importa quando
  alguém procura o que uma máquina fez no modelo dele;
- **a próxima chamada decide** o destino de um grupo abandonado. Sem
  temporizador: se o agente morrer, nada roda sozinho.

O que estes testes trancam são os casos que PERDEM trabalho de alguém. O que
eles não provam: que o Revit assimila o grupo. Isso só numa máquina com Revit.
"""

import pytest

from revit_mcp.job_group import (
    ASSIMILATE,
    NOTHING,
    OPEN,
    ROLLBACK,
    ROLLBACK_THEN_OPEN,
    JobGroups,
)


@pytest.fixture
def grupos():
    return JobGroups()


class TestComecar:
    def test_o_primeiro_trabalho_abre_o_grupo(self, grupos):
        d = grupos.begin("job-1")
        assert d.action == OPEN and d.ok
        assert grupos.open_job == "job-1"

    def test_comecar_o_MESMO_trabalho_de_novo_nao_descarta_nada(self, grupos):
        # Um "começar" repetido não é trabalho novo: é a resposta anterior que
        # se perdeu no caminho. Descartar aqui jogaria fora o que o agente já
        # tinha feito.
        grupos.begin("job-1")
        d = grupos.begin("job-1")
        assert d.action == NOTHING and d.ok
        assert grupos.open_job == "job-1"

    def test_um_trabalho_NOVO_descarta_o_que_ficou_aberto(self, grupos):
        # É a regra que o Artur escolheu: a próxima chamada decide. O grupo
        # abandonado some quando alguém volta a trabalhar, e não por um relógio.
        grupos.begin("job-1")
        d = grupos.begin("job-2")
        assert d.action == ROLLBACK_THEN_OPEN
        assert d.discarded_job == "job-1"
        assert grupos.open_job == "job-2"

    def test_o_descarte_e_DITO_e_nao_acontece_calado(self, grupos):
        # Alguém vai procurar por que o modelo voltou atrás. Sem esta frase, a
        # resposta é "não sei".
        grupos.begin("job-1")
        d = grupos.begin("job-2")
        assert "job-1" in d.message and "discard" in d.message

    @pytest.mark.parametrize("vazio", [None, "", "   "])
    def test_trabalho_sem_nome_e_RECUSADO(self, grupos, vazio):
        # Um grupo sem nome não pode ser fechado por nome depois — só por
        # acidente.
        d = grupos.begin(vazio)
        assert d.action == NOTHING and not d.ok
        assert grupos.open_job is None


class TestFechar:
    def test_confirmar_o_trabalho_aberto_assimila(self, grupos):
        grupos.begin("job-1")
        d = grupos.commit("job-1")
        assert d.action == ASSIMILATE and d.ok
        assert grupos.open_job is None

    def test_descartar_o_trabalho_aberto_desfaz(self, grupos):
        grupos.begin("job-1")
        d = grupos.abort("job-1")
        assert d.action == ROLLBACK and d.ok
        assert grupos.open_job is None

    def test_confirmar_sem_nada_aberto_NAO_e_sucesso_silencioso(self, grupos):
        # O gate leria "confirmado" e acreditaria que um grupo envolveu o
        # trabalho, quando nada envolveu.
        d = grupos.commit("job-1")
        assert d.action == NOTHING and not d.ok

    def test_confirmar_trabalho_diferente_do_aberto_e_recusado(self, grupos):
        # Assimilar o grupo alheio tornaria permanente o trabalho de OUTRO
        # job, sob o nome deste.
        grupos.begin("job-1")
        d = grupos.commit("job-2")
        assert d.action == NOTHING and not d.ok
        assert grupos.open_job == "job-1", "o grupo do job-1 não podia ter sido mexido"

    def test_descartar_trabalho_diferente_do_aberto_e_recusado(self, grupos):
        grupos.begin("job-1")
        d = grupos.abort("job-2")
        assert d.action == NOTHING and not d.ok
        assert grupos.open_job == "job-1"

    def test_descartar_sem_nada_aberto_tambem_nao_e_sucesso(self, grupos):
        # Acontece quando o agente falha e manda descartar duas vezes. Dizer
        # "descartado" na segunda faria parecer que havia algo a desfazer.
        d = grupos.abort("job-1")
        assert d.action == NOTHING and not d.ok
        assert "no job is open" in d.message

    def test_confirmar_duas_vezes_nao_assimila_duas_vezes(self, grupos):
        grupos.begin("job-1")
        assert grupos.commit("job-1").action == ASSIMILATE
        assert grupos.commit("job-1").action == NOTHING


class TestORevitSaiuDeBaixo:
    def test_esquecer_nao_e_desfazer(self, grupos):
        # Revit fechado, documento fechado: o que o grupo continha já foi
        # decidido por ele. Fingir que ainda dá para desfazer faria o próximo
        # "começar" tentar desfazer um grupo que não existe mais.
        grupos.begin("job-1")
        assert grupos.forget() == "job-1"
        assert grupos.open_job is None
        assert grupos.begin("job-2").action == OPEN

    def test_esquecer_sem_nada_aberto_nao_inventa_trabalho(self, grupos):
        assert grupos.forget() is None


class TestOCicloInteiro:
    def test_sucesso_do_comeco_ao_fim(self, grupos):
        assert grupos.begin("job-1").action == OPEN
        assert grupos.commit("job-1").action == ASSIMILATE
        assert grupos.open_job is None

    def test_falha_no_meio_desfaz_tudo(self, grupos):
        assert grupos.begin("job-1").action == OPEN
        assert grupos.abort("job-1").action == ROLLBACK
        assert grupos.open_job is None

    def test_agente_abandona_e_o_proximo_limpa(self, grupos):
        grupos.begin("job-1")  # e some
        d = grupos.begin("job-2")
        assert d.action == ROLLBACK_THEN_OPEN
        assert grupos.commit("job-2").action == ASSIMILATE


class TestAFormaDaResposta:
    """O que a rota devolve é o que alguém vai ler depois para entender por que
    o modelo voltou atrás. A forma importa tanto quanto a decisão."""

    def test_a_resposta_traz_acao_frase_e_se_deu_certo(self, grupos):
        d = grupos.begin("job-1").to_dict()
        assert set(d) == {"action", "message", "ok"}
        assert d["action"] == OPEN and d["ok"] is True
        assert "job-1" in d["message"]

    def test_o_trabalho_descartado_aparece_por_NOME_na_resposta(self, grupos):
        # Não basta dizer "descartei um grupo": qual, é o que a pessoa precisa
        # saber para procurar o que se perdeu.
        grupos.begin("job-1")
        d = grupos.begin("job-2").to_dict()
        assert d["discarded_job"] == "job-1"

    def test_quando_nada_foi_descartado_o_campo_nao_aparece(self, grupos):
        # Campo presente com valor nulo leria como "descartei nada", que é
        # ambíguo com "descartei algo sem nome".
        assert "discarded_job" not in grupos.begin("job-1").to_dict()

    def test_recusa_sai_com_ok_falso_e_o_motivo_escrito(self, grupos):
        d = grupos.commit("job-9").to_dict()
        assert d["ok"] is False
        assert "no job is open" in d["message"]

    def test_descartar_sem_nome_e_recusado_como_confirmar(self, grupos):
        grupos.begin("job-1")
        d = grupos.abort(None).to_dict()
        assert d["ok"] is False
        assert grupos.open_job == "job-1"


class TestOEnsaio:
    """Dry-run: executa de verdade e desfaz no fim.

    É o maior salto de confiança do fork. O plano de aprovação hoje é PROSA
    que o agente escreveu, e o servidor só exige que ela não esteja vazia —
    nada confere se descreve o que vai acontecer, e nada poderia. Com o
    ensaio, o plano passa a ser o relatório do que aconteceu numa execução
    de verdade que foi desfeita.
    """

    def test_o_ensaio_desfaz_no_fim_em_vez_de_assimilar(self, grupos):
        grupos.begin("job-1", dry_run=True)
        d = grupos.commit("job-1")
        assert d.action == ROLLBACK, "um ensaio que assimila não é ensaio: persistiu"
        assert "nothing persisted" in d.message

    def test_o_trabalho_de_verdade_continua_assimilando(self, grupos):
        grupos.begin("job-1")
        assert grupos.commit("job-1").action == ASSIMILATE

    def test_a_resposta_diz_que_e_ensaio_desde_o_comeco(self, grupos):
        # Quem lê o registro precisa saber, na primeira linha, que nada disso
        # vai ficar — e não descobrir só no fim.
        assert "rehearsal" in grupos.begin("job-1", dry_run=True).message
        assert grupos.dry_run is True

    def test_trabalho_de_VERDADE_comecado_por_cima_de_um_ensaio_nao_herda_o_ensaio(self, grupos):
        # Este é o caso que perde trabalho de gente: o ensaio ficou aberto, um
        # job de verdade começa por cima, e se herdasse o modo tudo o que ele
        # fizesse seria desfeito no fim — o arquiteto aprovaria e nada teria
        # acontecido, sem uma linha explicando por quê.
        grupos.begin("job-1", dry_run=True)
        grupos.begin("job-2")
        assert grupos.dry_run is False
        assert grupos.commit("job-2").action == ASSIMILATE

    def test_depois_do_ensaio_o_proximo_trabalho_nao_herda_o_modo(self, grupos):
        # Herdar faria um trabalho de verdade ser silenciosamente desfeito —
        # o arquiteto aprovaria e nada aconteceria.
        grupos.begin("job-1", dry_run=True)
        grupos.commit("job-1")
        grupos.begin("job-2")
        assert grupos.dry_run is False
        assert grupos.commit("job-2").action == ASSIMILATE


class TestOQueOEnsaioRELATA:
    def test_soma_o_que_cada_chamada_teria_mudado(self, grupos):
        grupos.begin("job-1", dry_run=True)
        grupos.record({"created": ["1"], "modified": [], "deleted": [], "measurements": {}})
        grupos.record({"created": ["2"], "modified": ["9"], "deleted": [], "measurements": {}})
        r = grupos.rehearsal()
        assert r["created"] == ["1", "2"]
        assert r["modified"] == ["9"]

    def test_o_mesmo_elemento_em_duas_chamadas_conta_UMA(self, grupos):
        # O agente que cria e depois modifica a mesma parede mexeu numa
        # parede; um plano dizendo "2" pede aprovação sobre estrago maior do
        # que o real.
        grupos.begin("job-1", dry_run=True)
        grupos.record({"created": ["7"], "modified": [], "deleted": [], "measurements": {}})
        grupos.record({"created": ["7"], "modified": [], "deleted": [], "measurements": {}})
        assert grupos.rehearsal()["created"] == ["7"]

    def test_as_medicoes_de_todas_as_chamadas_entram(self, grupos):
        # É o que permitiria conferir a norma ANTES de qualquer escrita:
        # "este projeto ficaria não conforme se você aprovar".
        grupos.begin("job-1", dry_run=True)
        for i in (1, 2):
            grupos.record(
                {
                    "created": [],
                    "modified": [],
                    "deleted": [],
                    "measurements": {"ambientes": [{"id": str(i), "uso": "dormitorio", "medicoes": {}}]},
                }
            )
        assert len(grupos.rehearsal()["measurements"]["ambientes"]) == 2

    def test_o_acumulado_e_por_TRABALHO_e_nao_vaza_para_o_seguinte(self, grupos):
        # Vazar faria o plano de aprovação de um job mostrar o que outro teria
        # mudado — e alguém aprovaria uma coisa lendo outra.
        grupos.begin("job-1", dry_run=True)
        grupos.record({"created": ["1"], "modified": [], "deleted": [], "measurements": {}})
        grupos.begin("job-2", dry_run=True)
        assert grupos.rehearsal()["created"] == []


class TestOQueOEnsaioNAODesfaz:
    """Dry-run não é gratuito nem inócuo: ele EXECUTA.

    O que saiu do modelo já saiu. Um ensaio que se apresenta como "nada
    aconteceu" enquanto um PDF foi escrito na área de trabalho do arquiteto é
    a mentira calada que este módulo existe para não contar.
    """

    def test_exportar_e_avisado_pelo_NOME_do_efeito(self, grupos):
        grupos.begin("job-1", dry_run=True)
        grupos.record({"created": [], "modified": [], "deleted": [], "measurements": {}},
                      route="/export_sheets_pdf/")
        assert grupos.rehearsal()["not_undone"] == ["arquivos exportados ficam no disco"]

    def test_sem_efeito_que_escapa_o_campo_nao_aparece(self, grupos):
        # Um aviso vazio em toda resposta ensina a pessoa a ignorar o campo.
        grupos.begin("job-1", dry_run=True)
        grupos.record({"created": ["1"], "modified": [], "deleted": [], "measurements": {}},
                      route="/create_walls/")
        assert "not_undone" not in grupos.rehearsal()

    def test_o_mesmo_aviso_nao_repete_por_duas_chamadas(self, grupos):
        grupos.begin("job-1", dry_run=True)
        for _ in range(3):
            grupos.record({}, route="/export_dwg/")
        assert len(grupos.rehearsal()["not_undone"]) == 1

    def test_avisos_diferentes_saem_todos(self, grupos):
        grupos.begin("job-1", dry_run=True)
        grupos.record({}, route="/export_pdf/")
        grupos.record({}, route="/reload_link/")
        assert len(grupos.rehearsal()["not_undone"]) == 2
