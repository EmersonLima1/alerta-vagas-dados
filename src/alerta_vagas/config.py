"""Configurações do alerta de vagas.

Tudo que é "regra de negócio" (cargos, níveis, idade máxima) fica aqui,
separado da lógica, para que ajustar o filtro não exija mexer no código.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Termos enviados para a busca da fonte. A busca é ampla de propósito:
# o filtro fino (cargo + nível) é feito depois, em filtros.py.
TERMOS_BUSCA: list[str] = [
    "analista de dados",
    "cientista de dados",
    "engenheiro de dados",
    "engenharia de dados",
    "analista de bi",
    "business intelligence",
    "data analyst",
    "data scientist",
    "data engineer",
]

# Cada cargo aceito: padrões (regex, sem acento e em minúsculas) que
# identificam o cargo no título + níveis aceitos para ele.
# Níveis possíveis: "junior", "pleno", "senior", "estagio", "nao_informado".
CARGOS: dict[str, dict] = {
    "Analista de Dados": {
        "padroes": [r"analista de dados", r"data analyst", r"analista de analytics"],
        "niveis": {"junior", "pleno"},
    },
    "Analista de BI": {
        "padroes": [
            r"analista de bi\b",
            r"analista (de )?business intelligence",
            r"\bbi analyst",
            r"business intelligence analyst",
        ],
        "niveis": {"junior", "pleno"},
    },
    "Cientista de Dados": {
        "padroes": [r"cientista de dados", r"data scientist"],
        "niveis": {"junior"},
    },
    "Engenheiro de Dados": {
        "padroes": [
            r"engenheir[oa] de dados",
            r"engenharia de dados",
            r"data engineer",
        ],
        "niveis": {"junior"},
    },
}


@dataclass
class Config:
    # Vagas publicadas há mais de N dias são ignoradas.
    max_dias: int = 7
    # Aceitar vagas cujo título não diz o nível (muito comum na Gupy).
    aceitar_nivel_nao_informado: bool = True
    # Quantas vagas por mensagem de WhatsApp (mensagens longas ficam ruins de ler).
    vagas_por_mensagem: int = 5
    # Teto de vagas enviadas por execução, para evitar "enxurrada" na 1ª execução.
    max_vagas_por_execucao: int = 20
    # Entradas do arquivo de estado mais velhas que isso são descartadas.
    dias_retencao_estado: int = 60
    caminho_estado: str = "data/vagas_enviadas.json"
    termos_busca: list[str] = field(default_factory=lambda: list(TERMOS_BUSCA))

    @classmethod
    def do_ambiente(cls) -> "Config":
        """Permite sobrescrever alguns valores por variáveis de ambiente
        (útil para testar no GitHub Actions sem alterar código)."""
        cfg = cls()
        if v := os.getenv("MAX_DIAS"):
            cfg.max_dias = int(v)
        if v := os.getenv("ACEITAR_NIVEL_NAO_INFORMADO"):
            cfg.aceitar_nivel_nao_informado = v.strip().lower() in {"1", "true", "sim"}
        if v := os.getenv("MAX_VAGAS_POR_EXECUCAO"):
            cfg.max_vagas_por_execucao = int(v)
        return cfg
