"""Testes puros: python3 -m unittest discover -s tests -p test_salas.py -v."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


RAIZ = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dominio_salas", RAIZ / "servidor-mcp/salas.py")
salas = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(salas)


def h(hora, dia="2026-11-03"):
    return f"{dia}T{hora}:00-03:00"


class AgendaSalasTests(unittest.TestCase):
    def setUp(self):
        self.agenda = salas.AgendaSalas.carregar()

    def test_carrega_starter_e_versao_da_politica(self):
        self.assertEqual(len(self.agenda.listar_salas()), 5)
        self.assertEqual(
            [reserva["id"] for reserva in self.agenda.listar_reservas()],
            ["res-0001", "res-0002"],
        )
        self.assertEqual(self.agenda.politica, "2026-11-01")

    def test_caminho_padrao_nao_depende_do_cwd(self):
        with patch("pathlib.Path.cwd", side_effect=AssertionError("nao usar cwd")):
            agenda = salas.AgendaSalas.carregar()
        self.assertEqual(agenda.listar_salas(), self.agenda.listar_salas())

    def test_copias_profundas_das_entradas_e_saidas(self):
        catalogo = self.agenda.listar_salas()
        reservas = self.agenda.listar_reservas()
        agenda = salas.AgendaSalas(catalogo, reservas, "versao-teste")
        original = (agenda.listar_salas(), agenda.listar_reservas())
        catalogo[0]["recursos"].append("mutacao")
        catalogo.clear()
        reservas[0]["responsavel"] = "mutacao"
        reservas.clear()
        saida_salas = agenda.listar_salas()
        saida_salas[0]["recursos"].append("mutacao")
        saida_reservas = agenda.listar_reservas()
        saida_reservas[0]["responsavel"] = "mutacao"
        self.assertEqual((agenda.listar_salas(), agenda.listar_reservas()), original)

    def test_ids_sequenciais_acima_dos_iniciais(self):
        ids = [
            self.agenda.reservar_sala(sala, h("09:00"), h("10:00"), "Doc")["reserva"]
            for sala in ("sala-aquario", "sala-porao", "sala-garagem")
        ]
        self.assertEqual(ids, ["res-0003", "res-0004", "res-0005"])
        todos = [reserva["id"] for reserva in self.agenda.listar_reservas()]
        self.assertEqual(len(todos), len(set(todos)))

    def test_sequencia_usa_maximo_nao_quantidade_nem_ultima_posicao(self):
        reservas = self.agenda.listar_reservas()
        reservas[0]["id"] = "res-0042"
        agenda = salas.AgendaSalas(self.agenda.listar_salas(), reservas, "teste")
        reserva = agenda.reservar_sala("sala-aquario", h("09:00"), h("10:00"), "Doc")
        self.assertEqual(reserva["reserva"], "res-0043")

    def test_agenda_sem_reservas_comeca_em_um(self):
        agenda = salas.AgendaSalas(self.agenda.listar_salas(), [], "teste")
        reserva = agenda.reservar_sala("sala-aquario", h("09:00"), h("10:00"), "Doc")
        self.assertEqual(reserva["reserva"], "res-0001")

    def test_criacao_e_consultas_nunca_gravam_dados(self):
        arquivos = list((RAIZ / "dados").iterdir())
        antes = {arquivo: arquivo.read_bytes() for arquivo in arquivos}
        # Além de comparar bytes, proíbe abertura para escrita durante operações.
        abrir = Path.open

        def somente_leitura(caminho, mode="r", *args, **kwargs):
            self.assertFalse(any(flag in mode for flag in "wax+"), mode)
            return abrir(caminho, mode, *args, **kwargs)

        with patch.object(Path, "open", somente_leitura):
            agenda = salas.AgendaSalas.carregar(RAIZ / "dados")
            agenda.reservar_sala("sala-aquario", h("09:00"), h("10:00"), "Doc")
            agenda.consultar_disponibilidade("sala-aquario", h("09:00"), h("10:00"))
            agenda.alternativas("sala-aquario", h("09:00"), h("10:00"))
        self.assertEqual(antes, {arquivo: arquivo.read_bytes() for arquivo in arquivos})

    def test_nova_agenda_perde_so_reservas_de_execucao(self):
        self.agenda.reservar_sala("sala-aquario", h("09:00"), h("10:00"), "Doc")
        nova = salas.AgendaSalas.carregar()
        self.assertEqual(len(nova.listar_reservas()), 2)
        self.assertTrue(nova.consultar_disponibilidade("sala-aquario", h("09:00"), h("10:00"))["livre"])
        self.assertFalse(nova.consultar_disponibilidade("sala-garagem", h("14:00"), h("15:00"))["livre"])

    def _operacoes(self, agenda, sala, inicio, fim):
        return {
            "consulta": lambda: agenda.consultar_disponibilidade(sala, inicio, fim),
            "reserva": lambda: agenda.reservar_sala(sala, inicio, fim, "Doc"),
            "alternativas": lambda: agenda.alternativas(sala, inicio, fim),
        }

    def test_mensagens_exatas_e_ausencia_de_mutacao(self):
        casos = (
            ("sala-delorean", "09:00", "10:00", "Sala inexistente: sala-delorean"),
            ("sala-aquario", "07:00", "08:00", "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"),
            ("sala-aquario", "19:00", "21:00", "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"),
            ("sala-aquario", "09:00", "12:00", "Duracao acima do limite: a politica permite no maximo 2 horas"),
            ("sala-aquario", "10:00", "09:00", "Intervalo invalido: fim deve ser posterior a inicio"),
            ("sala-aquario", "10:00", "10:00", "Intervalo invalido: fim deve ser posterior a inicio"),
        )
        antes = self.agenda.listar_reservas()
        for sala, inicio, fim, mensagem in casos:
            for nome, executar in self._operacoes(self.agenda, sala, h(inicio), h(fim)).items():
                with self.subTest(operacao=nome, sala=sala, inicio=inicio, fim=fim):
                    with self.assertRaises(salas.ErroDominio) as erro:
                        executar()
                    self.assertEqual(str(erro.exception), mensagem)
                    self.assertEqual(self.agenda.listar_reservas(), antes)

    def test_precedencia_em_violacoes_multiplas(self):
        casos = (
            ("sala-inexistente", h("22:00"), h("01:00"), "Sala inexistente: sala-inexistente"),
            ("sala-inexistente", "invalido", "invalido", "Sala inexistente: sala-inexistente"),
            ("sala-aquario", h("22:00"), h("01:00"), salas.ERRO_INTERVALO),
            ("sala-aquario", h("07:00"), h("12:00"), salas.ERRO_JANELA),
            ("sala-aquario", h("09:00"), h("09:00", "2026-11-04"), salas.ERRO_JANELA),
        )
        for sala, inicio, fim, mensagem in casos:
            for nome, executar in self._operacoes(self.agenda, sala, inicio, fim).items():
                with self.subTest(operacao=nome, sala=sala, inicio=inicio, fim=fim):
                    with self.assertRaises(salas.ErroDominio) as erro:
                        executar()
                    self.assertEqual(str(erro.exception), mensagem)

    def test_bordas_inclusivas_duas_horas_e_data_passada(self):
        for dia in ("2026-11-03", "2000-01-01"):
            for inicio, fim in (("08:00", "10:00"), ("18:00", "20:00")):
                with self.subTest(dia=dia, inicio=inicio):
                    agenda = salas.AgendaSalas.carregar()
                    self.assertTrue(agenda.consultar_disponibilidade("sala-aquario", h(inicio, dia), h(fim, dia))["livre"])
                    self.assertTrue(agenda.reservar_sala("sala-aquario", h(inicio, dia), h(fim, dia), "Doc")["reservado"])

    def test_limites_com_precisao_de_microssegundos(self):
        casos = (
            ("2026-11-03T07:59:59.999999-03:00", h("09:00"), salas.ERRO_JANELA),
            (h("19:00"), "2026-11-03T20:00:00.000001-03:00", salas.ERRO_JANELA),
            (h("09:00"), "2026-11-03T11:00:00.000001-03:00", salas.ERRO_DURACAO),
        )
        for inicio, fim, mensagem in casos:
            with self.subTest(inicio=inicio, fim=fim):
                with self.assertRaises(salas.ErroDominio) as erro:
                    self.agenda.validar_intervalo("sala-aquario", inicio, fim)
                self.assertEqual(str(erro.exception), mensagem)

    def test_offsets_equivalentes_e_preservacao_dos_argumentos(self):
        inicio, fim = "2026-11-03T12:00:00Z", "2026-11-03T15:00:00+02:00"
        consulta = self.agenda.consultar_disponibilidade("sala-aquario", inicio, fim)
        self.assertEqual(consulta, self.agenda.consultar_disponibilidade("sala-aquario", h("09:00"), h("10:00")))
        reserva = self.agenda.reservar_sala("sala-aquario", inicio, fim, "Dra. Emília Brown")
        self.assertEqual((reserva["inicio"], reserva["fim"], reserva["responsavel"]), (inicio, fim, "Dra. Emília Brown"))
        self.assertFalse(self.agenda.consultar_disponibilidade("sala-aquario", h("09:00"), h("10:00"))["livre"])

    def test_offset_nao_burla_janela_nem_dia_local(self):
        casos = (
            ("2026-11-03T08:00:00Z", "2026-11-03T09:00:00Z"),
            ("2026-11-03T20:00:00-03:00", "2026-11-04T08:00:00-03:00"),
        )
        for inicio, fim in casos:
            with self.subTest(inicio=inicio, fim=fim):
                with self.assertRaises(salas.ErroDominio) as erro:
                    self.agenda.validar_intervalo("sala-aquario", inicio, fim)
                self.assertEqual(str(erro.exception), salas.ERRO_JANELA)

    def test_ordem_do_intervalo_compara_instantes_nao_texto(self):
        for fim in ("2026-11-03T13:00:00+01:00", "2026-11-03T13:00:00+02:00"):
            with self.subTest(fim=fim):
                with self.assertRaises(salas.ErroDominio) as erro:
                    self.agenda.validar_intervalo("sala-aquario", "2026-11-03T12:00:00Z", fim)
                self.assertEqual(str(erro.exception), salas.ERRO_INTERVALO)

    def test_datas_invalidas_ou_sem_offset_sao_rejeitadas_sem_mutacao(self):
        for invalido in ("", "nao-data", "2026-11-03", "2026-11-03T09:00:00", "2026-02-30T09:00:00-03:00", None, 42):
            for campo in ("inicio", "fim"):
                inicio, fim = (invalido, h("10:00")) if campo == "inicio" else (h("09:00"), invalido)
                for nome, executar in self._operacoes(self.agenda, "sala-aquario", inicio, fim).items():
                    with self.subTest(operacao=nome, campo=campo, valor=invalido):
                        with self.assertRaises(ValueError) as erro:
                            executar()
                        self.assertNotIsInstance(erro.exception, salas.ErroDominio)
                        self.assertEqual(len(self.agenda.listar_reservas()), 2)

    def test_disponibilidade_livre_e_detalhes_do_conflito_inicial(self):
        self.assertEqual(self.agenda.consultar_disponibilidade("sala-aquario", h("14:00"), h("15:00")), {"sala": "sala-aquario", "livre": True, "conflitos": []})
        consulta = self.agenda.consultar_disponibilidade("sala-garagem", h("14:00"), h("15:00"))
        self.assertEqual(consulta, {"sala": "sala-garagem", "livre": False, "conflitos": [{"id": "res-0001", "inicio": h("14:00"), "fim": h("15:00"), "responsavel": "Marty"}]})
        consulta["conflitos"][0]["responsavel"] = "mutacao"
        self.assertEqual(self.agenda.listar_reservas()[0]["responsavel"], "Marty")

    def test_sobreposicao_parcial_inclusao_e_offsets(self):
        casos = (
            (h("13:30"), h("14:30")),
            (h("14:30"), h("15:30")),
            (h("14:15"), h("14:45")),
            (h("13:30"), h("15:30")),
            ("2026-11-03T17:00:00Z", "2026-11-03T18:00:00Z"),
        )
        for inicio, fim in casos:
            with self.subTest(inicio=inicio, fim=fim):
                consulta = self.agenda.consultar_disponibilidade("sala-garagem", inicio, fim)
                self.assertFalse(consulta["livre"])
                self.assertEqual(consulta["conflitos"][0]["id"], "res-0001")

    def test_reservas_adjacentes_nao_conflitam(self):
        for inicio, fim in (("13:00", "14:00"), ("15:00", "16:00")):
            with self.subTest(inicio=inicio):
                self.assertTrue(self.agenda.consultar_disponibilidade("sala-garagem", h(inicio), h(fim))["livre"])
                self.assertTrue(self.agenda.reservar_sala("sala-garagem", h(inicio), h(fim), "Doc")["reservado"])

    def test_consulta_retorna_todos_os_conflitos(self):
        for inicio, fim in (("09:00", "10:00"), ("10:00", "11:00")):
            self.agenda.reservar_sala("sala-aquario", h(inicio), h(fim), "Doc")
        consulta = self.agenda.consultar_disponibilidade("sala-aquario", h("09:00"), h("11:00"))
        self.assertEqual([conflito["id"] for conflito in consulta["conflitos"]], ["res-0003", "res-0004"])

    def test_reserva_completa_e_consulta_posterior(self):
        reserva = self.agenda.reservar_sala("sala-aquario", h("09:00"), h("10:00"), "Doc")
        self.assertEqual(reserva, {"reserva": "res-0003", "reservado": True, "sala": "sala-aquario", "inicio": h("09:00"), "fim": h("10:00"), "responsavel": "Doc", "politica": "2026-11-01", "motivo": None})
        self.assertEqual(json.loads(json.dumps(reserva)), reserva)
        reserva["responsavel"] = "mutacao"
        consulta = self.agenda.consultar_disponibilidade("sala-aquario", h("09:00"), h("10:00"))
        self.assertFalse(consulta["livre"])
        self.assertEqual(consulta["conflitos"][0]["responsavel"], "Doc")

    def test_versao_nao_e_hardcoded_na_reserva(self):
        agenda = salas.AgendaSalas(self.agenda.listar_salas(), [], "versao-injetada")
        reserva = agenda.reservar_sala("sala-aquario", h("09:00"), h("10:00"), "Doc")
        self.assertEqual(reserva["politica"], "versao-injetada")

    def test_conflito_intermediario_nao_muta_nem_consumе_id(self):
        antes = self.agenda.listar_reservas()
        with self.assertRaises(salas.ConflitoReserva) as erro:
            self.agenda.reservar_sala("sala-garagem", h("14:00"), h("15:00"), "Doc")
        self.assertEqual(erro.exception.sala, "sala-garagem")
        self.assertEqual(erro.exception.conflitos[0]["id"], "res-0001")
        erro.exception.conflitos[0]["responsavel"] = "mutacao"
        self.assertEqual(self.agenda.listar_reservas(), antes)
        reserva = self.agenda.reservar_sala("sala-aquario", h("09:00"), h("10:00"), "Doc")
        self.assertEqual(reserva["reserva"], "res-0003")

    def test_alternativas_iniciais_capacidade_e_ordem(self):
        antes = self.agenda.listar_reservas()
        self.assertEqual(self.agenda.alternativas("sala-garagem", h("14:00"), h("15:00")), ["sala-fusca", "sala-mirante"])
        self.assertEqual(self.agenda.alternativas("sala-fusca", h("16:00"), h("17:00")), ["sala-garagem", "sala-mirante"])
        self.assertEqual(self.agenda.listar_reservas(), antes)

    def test_alternativas_desempate_por_id_e_corte_de_tres(self):
        self.agenda.reservar_sala("sala-aquario", h("09:00"), h("10:00"), "Doc")
        # Fusca vem após Garagem no JSON, mas antes por id; Mirante é a quarta.
        self.assertEqual(self.agenda.alternativas("sala-aquario", h("09:00"), h("10:00")), ["sala-porao", "sala-fusca", "sala-garagem"])

    def test_alternativas_filtram_ocupadas_e_podem_ser_unica_ou_nenhuma(self):
        self.agenda.reservar_sala("sala-fusca", h("14:00"), h("15:00"), "Doc")
        self.assertEqual(self.agenda.alternativas("sala-garagem", h("14:00"), h("15:00")), ["sala-mirante"])
        self.agenda.reservar_sala("sala-mirante", h("14:00"), h("15:00"), "Doc")
        self.assertEqual(self.agenda.alternativas("sala-garagem", h("14:00"), h("15:00")), [])
        self.assertEqual(self.agenda.alternativas("sala-mirante", h("14:00"), h("15:00")), [])

    def test_alternativas_nao_dependem_da_ordem_do_catalogo(self):
        catalogo = list(reversed(self.agenda.listar_salas()))
        agenda = salas.AgendaSalas(catalogo, self.agenda.listar_reservas(), "teste")
        self.assertEqual(agenda.alternativas("sala-aquario", h("09:00"), h("10:00")), ["sala-porao", "sala-fusca", "sala-garagem"])

    def test_alternativas_reconsultam_estado_e_aceitam_adjacencia(self):
        self.agenda.reservar_sala("sala-fusca", h("13:00"), h("14:00"), "Doc")
        alternativas = self.agenda.alternativas("sala-garagem", h("14:00"), h("15:00"))
        alternativas.clear()
        self.assertEqual(self.agenda.alternativas("sala-garagem", h("14:00"), h("15:00")), ["sala-fusca", "sala-mirante"])
        self.agenda.reservar_sala("sala-fusca", h("14:00"), h("15:00"), "Outro")
        self.assertEqual(self.agenda.alternativas("sala-garagem", h("14:00"), h("15:00")), ["sala-mirante"])
        with self.assertRaises(salas.ConflitoReserva):
            self.agenda.reservar_sala("sala-fusca", h("14:00"), h("15:00"), "Doc")


if __name__ == "__main__":
    unittest.main()
