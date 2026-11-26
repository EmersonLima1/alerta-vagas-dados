"""Memória das vagas já enviadas (para não repetir).

Guardamos um JSON versionado no próprio repositório:
    {"gupy:123": "2026-11-26T12:00:00+00:00", ...}   (chave -> quando foi enviada)

Por que um arquivo no repo e não o cache do GitHub Actions?
- o cache é apagado após 7 dias sem uso e pode ser despejado a qualquer momento;
- o arquivo no repo tem histórico (git log mostra o que foi enviado e quando);
- é simples de inspecionar e corrigir à mão.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def carregar(caminho: str | Path) -> dict[str, str]:
    caminho = Path(caminho)
    if not caminho.exists():
        log.info("Estado não encontrado em %s; começando vazio", caminho)
        return {}
    conteudo = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(conteudo, dict):
        raise ValueError(f"Estado inválido em {caminho}: esperado objeto JSON")
    return conteudo


def podar(estado: dict[str, str], dias_retencao: int, agora: datetime | None = None) -> dict[str, str]:
    """Remove entradas antigas. Como só enviamos vagas com até `max_dias`,
    lembrar de vagas enviadas há 60 dias já é mais que suficiente."""
    agora = agora or datetime.now(timezone.utc)
    limite = agora - timedelta(days=dias_retencao)
    return {k: v for k, v in estado.items() if datetime.fromisoformat(v) >= limite}


def salvar(estado: dict[str, str], caminho: str | Path) -> None:
    """Grava de forma atômica: escreve num temporário e renomeia.
    Se o processo morrer no meio, o arquivo antigo continua íntegro."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=caminho.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(estado.items())), f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, caminho)
