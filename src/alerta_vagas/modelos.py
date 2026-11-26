"""Modelo de dados comum a todas as fontes.

Cada fonte (Gupy hoje, outras no futuro) converte o formato dela para
`Vaga`. Assim filtros, estado e envio não dependem da fonte.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Vaga:
    fonte: str            # ex.: "gupy"
    id_fonte: str         # id da vaga dentro da fonte
    titulo: str
    empresa: str
    url: str
    publicada_em: datetime | None   # sempre com timezone (UTC)
    remota: bool
    pais: str             # como veio da fonte; "" se não informado
    cidade: str = ""
    estado: str = ""

    @property
    def chave(self) -> str:
        """Identificador único usado para não enviar a mesma vaga duas vezes."""
        return f"{self.fonte}:{self.id_fonte}"
