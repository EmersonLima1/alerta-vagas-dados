"""Regras que decidem se uma vaga interessa.

Ordem: remota -> Brasil -> recente -> cargo -> nível.
Cada regra é uma função pequena e testável isoladamente.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone

from .config import CARGOS, Config
from .modelos import Vaga

PAISES_BRASIL = {"brasil", "brazil", "br"}

# Termos no título que indicam vaga fora do Brasil, mesmo com país vazio.
TERMOS_INTERNACIONAIS = [r"\binternational\b", r"\binternacional\b", r"\blatam\b", r"\busa\b", r"\beurope\b"]

# Padrões de nível no título (já sem acento e em minúsculas).
# Na Gupy é comum usar algarismos romanos: I = júnior, II = pleno, III = sênior.
NIVEIS = {
    "estagio": [r"\bestagi", r"\bintern(ship)?\b", r"\btrainee\b", r"\baprendiz\b"],
    "senior": [
        r"\bsenior\b", r"\bsr\.?\b", r"\biii\b", r"\biv\b", r"\bespecialista\b",
        r"\blead\b", r"\blider\b", r"\bcoordenador", r"\bgerente\b", r"\bhead\b",
        r"\bprincipal\b", r"\bstaff\b", r"\bmanager\b",
    ],
    "pleno": [r"\bpleno\b", r"\bpl\b", r"\bii\b", r"\bmid(-level)?\b"],
    "junior": [r"\bjunior\b", r"\bjr\.?\b", r"\bi\b", r"\bentry[- ]level\b"],
}


def normalizar_texto(texto: str) -> str:
    """Minúsculas e sem acentos: 'Júnior' -> 'junior'."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower()


def eh_remota(vaga: Vaga) -> bool:
    return vaga.remota


def eh_brasil(vaga: Vaga) -> bool:
    titulo = normalizar_texto(vaga.titulo)
    if any(re.search(p, titulo) for p in TERMOS_INTERNACIONAIS):
        return False
    pais = normalizar_texto(vaga.pais).strip()
    # País vazio: a Gupy é brasileira e muitas vagas remotas vêm sem país.
    # Aceitamos, mas o título já foi checado acima.
    return pais == "" or pais in PAISES_BRASIL


def eh_recente(vaga: Vaga, max_dias: int, agora: datetime | None = None) -> bool:
    if vaga.publicada_em is None:
        return False  # sem data não dá para garantir que não é antiga
    agora = agora or datetime.now(timezone.utc)
    return agora - vaga.publicada_em <= timedelta(days=max_dias)


def identificar_cargo(titulo: str) -> str | None:
    t = normalizar_texto(titulo)
    for cargo, regra in CARGOS.items():
        if any(re.search(p, t) for p in regra["padroes"]):
            return cargo
    return None


def identificar_nivel(titulo: str) -> str:
    """Devolve o nível mais "restritivo" encontrado no título.

    A ordem importa: 'Estágio' e 'Sênior' são checados antes de júnior,
    para que 'Analista de Dados Sr' nunca passe como júnior por engano.
    """
    t = normalizar_texto(titulo)
    for nivel, padroes in NIVEIS.items():
        if any(re.search(p, t) for p in padroes):
            return nivel
    return "nao_informado"


def avaliar(vaga: Vaga, cfg: Config, agora: datetime | None = None) -> tuple[bool, str]:
    """Retorna (aceita?, motivo). O motivo ajuda a depurar pelos logs."""
    if not eh_remota(vaga):
        return False, "nao_remota"
    if not eh_brasil(vaga):
        return False, "internacional"
    if not eh_recente(vaga, cfg.max_dias, agora):
        return False, "antiga_ou_sem_data"
    cargo = identificar_cargo(vaga.titulo)
    if cargo is None:
        return False, "cargo_fora_do_escopo"
    nivel = identificar_nivel(vaga.titulo)
    if nivel == "nao_informado":
        return (cfg.aceitar_nivel_nao_informado, f"{cargo}/nivel_nao_informado")
    if nivel in CARGOS[cargo]["niveis"]:
        return True, f"{cargo}/{nivel}"
    return False, f"nivel_{nivel}_nao_aceito_para_{cargo}"
