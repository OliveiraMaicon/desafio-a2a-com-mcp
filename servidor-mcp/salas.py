"""Domínio de salas, sem dependências de transporte ou do SDK MCP.

Cada AgendaSalas mantém cópias dos dados iniciais e das reservas criadas apenas
em memória. Carregar uma nova agenda (inclusive após restart) perde as reservas
de execução. Este módulo nunca grava em dados/.

Precedência das validações: sala existente, parsing com offset, intervalo
estritamente crescente, janela no mesmo dia UTC-03:00, duração máxima.
ErroDominio identifica as mensagens de negócio contratuais; ValueError simples
identifica datas malformadas/sem offset, cuja mensagem não é contratual.

ConflitoReserva é um resultado intermediário via exceção, nunca uma reserva
fictícia: não há mutação quando o intervalo está ocupado. A integração MCP
traduzirá esse caminho para MRTR na próxima change. O cálculo de alternativas
fica aqui; emissão de elicitation e proteção de requestState ficam fora daqui.
Não há promessa de idempotência, persistência ou transações concorrentes.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any


FUSO_POLITICA = timezone(timedelta(hours=-3))
ERRO_INTERVALO = "Intervalo invalido: fim deve ser posterior a inicio"
ERRO_JANELA = (
    "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"
)
ERRO_DURACAO = "Duracao acima do limite: a politica permite no maximo 2 horas"


class ErroDominio(ValueError):
    """Violação de negócio; o adaptador deverá preservar str(erro) no conteúdo."""


class ConflitoReserva(Exception):
    """Intervalo ocupado, sem escrita; o adaptador decide a negociação MRTR."""

    def __init__(self, sala: str, conflitos: list[dict[str, Any]]) -> None:
        self.sala = sala
        self.conflitos = deepcopy(conflitos)
        super().__init__(f"Intervalo ocupado na sala: {sala}")


def _instante(valor: str, campo: str) -> datetime:
    # Python 3.10 ainda não reconhece o sufixo Z em fromisoformat.
    try:
        instante = datetime.fromisoformat(
            valor[:-1] + "+00:00" if valor.endswith("Z") else valor
        )
        if instante.utcoffset() is None:
            raise ValueError
        return instante.astimezone(FUSO_POLITICA)
    except (AttributeError, TypeError, ValueError, OverflowError):
        raise ValueError(
            f"Instante invalido em {campo}: informe ISO 8601 com offset"
        ) from None


class AgendaSalas:
    """Armazenamento pequeno por processo; métodos retornam cópias destacadas."""

    def __init__(
        self,
        salas: list[dict[str, Any]],
        reservas: list[dict[str, Any]],
        politica: str,
    ) -> None:
        self._salas = {sala["id"]: deepcopy(sala) for sala in salas}
        self._reservas = deepcopy(reservas)
        self.politica = politica
        numeros = [
            int(match.group(1))
            for reserva in self._reservas
            if (match := re.fullmatch(r"res-(\d+)", reserva["id"]))
        ]
        self._proximo_id = max(numeros, default=0) + 1

    @classmethod
    def carregar(cls, diretorio_dados: str | Path | None = None) -> AgendaSalas:
        """Lê o starter, resolvendo o caminho padrão pelo módulo, não pelo cwd."""
        diretorio = (
            Path(diretorio_dados)
            if diretorio_dados is not None
            else Path(__file__).resolve().parents[1] / "dados"
        )
        salas = json.loads((diretorio / "salas.json").read_text(encoding="utf-8"))
        reservas = json.loads(
            (diretorio / "reservas.json").read_text(encoding="utf-8")
        )
        linhas = (diretorio / "politica-de-uso.md").read_text(
            encoding="utf-8"
        ).splitlines()
        if not linhas or not linhas[0].startswith("versao:"):
            raise ValueError("A politica deve declarar versao na primeira linha")
        politica = linhas[0].partition(":")[2].strip()
        if not politica:
            raise ValueError("A versao da politica nao pode ser vazia")
        return cls(salas, reservas, politica)

    def listar_salas(self) -> list[dict[str, Any]]:
        return deepcopy(list(self._salas.values()))

    def listar_reservas(self) -> list[dict[str, Any]]:
        return deepcopy(self._reservas)

    def validar_intervalo(
        self, sala: str, inicio: str, fim: str
    ) -> tuple[datetime, datetime]:
        """Valida sem consultar o relógio; retorna instantes em UTC-03:00.

        Mensagens seguem a precedência documentada no módulo, inclusive quando
        uma entrada viola mais de uma regra. As strings do pedido não mudam.
        """
        if sala not in self._salas:
            raise ErroDominio(f"Sala inexistente: {sala}")
        inicio_local = _instante(inicio, "inicio")
        fim_local = _instante(fim, "fim")
        if fim_local <= inicio_local:
            raise ErroDominio(ERRO_INTERVALO)
        if (
            inicio_local.date() != fim_local.date()
            or not time(8) <= inicio_local.time() <= time(20)
            or not time(8) <= fim_local.time() <= time(20)
        ):
            raise ErroDominio(ERRO_JANELA)
        if fim_local - inicio_local > timedelta(hours=2):
            raise ErroDominio(ERRO_DURACAO)
        return inicio_local, fim_local

    def _conflitos(
        self, sala: str, inicio: datetime, fim: datetime
    ) -> list[dict[str, Any]]:
        return [
            deepcopy(reserva)
            for reserva in self._reservas
            if reserva["sala"] == sala
            and inicio < _instante(reserva["fim"], "fim")
            and fim > _instante(reserva["inicio"], "inicio")
        ]

    def consultar_disponibilidade(
        self, sala: str, inicio: str, fim: str
    ) -> dict[str, Any]:
        inicio_local, fim_local = self.validar_intervalo(sala, inicio, fim)
        conflitos = self._conflitos(sala, inicio_local, fim_local)
        return {
            "sala": sala,
            "livre": not conflitos,
            "conflitos": [
                {campo: reserva[campo] for campo in ("id", "inicio", "fim", "responsavel")}
                for reserva in conflitos
            ],
        }

    def reservar_sala(
        self, sala: str, inicio: str, fim: str, responsavel: str
    ) -> dict[str, Any]:
        """Insere somente se livre; conflito levanta ConflitoReserva sem mutação."""
        inicio_local, fim_local = self.validar_intervalo(sala, inicio, fim)
        conflitos = self._conflitos(sala, inicio_local, fim_local)
        if conflitos:
            raise ConflitoReserva(sala, conflitos)
        reserva = {
            "id": f"res-{self._proximo_id:04d}",
            "sala": sala,
            "inicio": inicio,
            "fim": fim,
            "responsavel": responsavel,
        }
        self._reservas.append(reserva)
        self._proximo_id += 1
        return {
            "reserva": reserva["id"],
            "reservado": True,
            "sala": sala,
            "inicio": inicio,
            "fim": fim,
            "responsavel": responsavel,
            "politica": self.politica,
            "motivo": None,
        }

    def alternativas(self, sala: str, inicio: str, fim: str) -> list[str]:
        """IDs livres elegíveis, ordenados e limitados; não emite elicitation.

        Recebe sempre a sala do pedido original, inclusive após nova pausa MRTR,
        para não aumentar indevidamente a capacidade mínima de uma continuação.
        Não exige conflito: o chamador decide quando oferecer as alternativas.
        """
        inicio_local, fim_local = self.validar_intervalo(sala, inicio, fim)
        capacidade = self._salas[sala]["capacidade"]
        elegiveis = [
            candidata
            for candidata in self._salas.values()
            if candidata["id"] != sala
            and candidata["capacidade"] >= capacidade
            and not self._conflitos(candidata["id"], inicio_local, fim_local)
        ]
        elegiveis.sort(key=lambda candidata: (candidata["capacidade"], candidata["id"]))
        return [candidata["id"] for candidata in elegiveis[:3]]
