"""Testes isolados: python3 -m unittest discover -s tests -p test_pedidos.py -v."""

import json
from pathlib import Path
import unittest

from agente.pedidos import PedidoInvalido, parse_pedido


_INICIO = "2026-11-03T09:00:00-03:00"
_FIM = "2026-11-03T10:00:00-03:00"
_PREFIXO = f"reservar sala=sala-aquario inicio={_INICIO} fim={_FIM} responsavel="


class ParserPedidosTests(unittest.TestCase):
    def test_pedidos_validos_parametrizados(self):
        for sala, inicio, fim, responsavel in (
            ("sala-aquario", _INICIO, _FIM, "Doc"),
            ("sala-delorean", _INICIO, _FIM, "Marty McFly"),
            ("sala-futura", _INICIO, _FIM, "Dra. Emília  Brown"),
            ("qualquer-id", _INICIO, _FIM, "  Doc Brown  "),
            ("sala-aquario", _INICIO, _FIM, "Doc inicio=apelido"),
            (
                "sala-aquario",
                "2020-01-01T06:00:00Z",
                "2020-01-01T05:00:00Z",
                "Doc",
            ),
            (
                "sala-aquario",
                "2026-11-03T01:00:00.123456+00:00",
                "2026-11-03T23:00:00.654321+00:00",
                "Doc",
            ),
        ):
            with self.subTest(sala=sala, inicio=inicio, responsavel=responsavel):
                texto = (
                    f"reservar sala={sala} inicio={inicio} "
                    f"fim={fim} responsavel={responsavel}"
                )
                self.assertEqual(
                    parse_pedido(texto),
                    {
                        "sala": sala,
                        "inicio": inicio,
                        "fim": fim,
                        "responsavel": responsavel,
                    },
                )

    def test_aceita_espacos_entre_campos_sem_normalizar_responsavel(self):
        texto = (
            f"reservar  sala=sala-delorean   inicio={_INICIO} "
            f" fim={_FIM}  responsavel=Marty  McFly"
        )
        self.assertEqual(parse_pedido(texto)["responsavel"], "Marty  McFly")

    def test_exemplo_wire_inteiro(self):
        caminho = (
            Path(__file__).resolve().parents[1]
            / "exemplos/wire/08-a2a-send-message.json"
        )
        exemplo = json.loads(caminho.read_text(encoding="utf-8"))
        texto = exemplo["request"]["body"]["params"]["message"]["parts"][0]["text"]
        self.assertEqual(
            parse_pedido(texto),
            {
                "sala": "sala-garagem",
                "inicio": "2026-11-03T14:00:00-03:00",
                "fim": "2026-11-03T15:00:00-03:00",
                "responsavel": "Marty",
            },
        )

    def test_entradas_malformadas_parametrizadas(self):
        for texto in (
            "",
            "reserve uma sala para Doc",
            "escolha=sala-mirante",
            _PREFIXO,
            _PREFIXO + "   ",
            _PREFIXO.replace("reservar", "Reservar") + "Doc",
            " " + _PREFIXO + "Doc",
            _PREFIXO.replace("reservar ", "reservar\t") + "Doc",
            _PREFIXO.replace("sala=sala-aquario", "sala=") + "Doc",
            _PREFIXO.replace("sala=sala-aquario", "sala=sala aquario") + "Doc",
            _PREFIXO.replace("sala=sala-aquario", "sala==sala-aquario") + "Doc",
            _PREFIXO.replace(f"inicio={_INICIO}", "inicio=") + "Doc",
            _PREFIXO.replace(f"fim={_FIM}", "fim=") + "Doc",
            _PREFIXO.replace(f"inicio={_INICIO} ", "") + "Doc",
            _PREFIXO.replace(f"fim={_FIM}", f"fim={_FIM} extra=valor") + "Doc",
            _PREFIXO.replace("responsavel=", "responsável=") + "Doc",
            f"reservar inicio={_INICIO} sala=sala-aquario fim={_FIM} responsavel=Doc",
            _PREFIXO.replace(" inicio=", "\ninicio=") + "Doc",
            _PREFIXO + "Doc\nBrown",
            _PREFIXO + "Doc\rBrown",
            _PREFIXO + "Doc\n",
            None,
            42,
            b"reservar sala=sala-aquario",
            {},
        ):
            with self.subTest(texto=texto):
                with self.assertRaises(PedidoInvalido) as erro:
                    parse_pedido(texto)
                self.assertIsInstance(erro.exception, ValueError)
                self.assertEqual(
                    str(erro.exception),
                    "Pedido invalido: use reservar sala=<id> inicio=<iso8601> "
                    "fim=<iso8601> responsavel=<nome>",
                )

    def test_resultados_independentes_e_deterministicos(self):
        texto = _PREFIXO + "Doc Brown"
        primeiro = parse_pedido(texto)
        segundo = parse_pedido(texto)
        self.assertEqual(primeiro, segundo)
        self.assertIsNot(primeiro, segundo)
        primeiro["sala"] = "alterada-pelo-chamador"
        self.assertEqual(parse_pedido(texto), segundo)


if __name__ == "__main__":
    unittest.main()
