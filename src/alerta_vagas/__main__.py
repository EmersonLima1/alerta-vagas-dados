"""Ponto de entrada: `python -m alerta_vagas [--dry-run]`.

Fluxo (um mini ETL):
  1. Extrair  - buscar vagas nas fontes
  2. Transformar - filtrar (remota, Brasil, recente, cargo, nível) e remover já enviadas
  3. Carregar - enviar pelo WhatsApp e registrar no estado o que foi enviado
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime, timezone

from . import estado as estado_mod
from .config import Config
from .filtros import avaliar
from .fontes import gupy
from .notificador import CallMeBot, Console, ErroEnvio, Notificador, montar_mensagens, texto_do_grupo

log = logging.getLogger("alerta_vagas")


def executar(cfg: Config, notificador: Notificador, buscar=gupy.buscar, agora: datetime | None = None) -> int:
    """Executa uma rodada. Devolve quantas vagas foram enviadas."""
    agora = agora or datetime.now(timezone.utc)
    estado = estado_mod.podar(estado_mod.carregar(cfg.caminho_estado), cfg.dias_retencao_estado, agora)

    vagas = buscar(cfg.termos_busca)

    aceitas, motivos = [], Counter()
    for vaga in vagas:
        ok, motivo = avaliar(vaga, cfg, agora)
        if ok and vaga.chave in estado:
            ok, motivo = False, "ja_enviada"
        motivos[motivo if not ok else "aceita"] += 1
        if ok:
            aceitas.append((vaga, motivo))
    log.info("Resumo do filtro: %s", dict(motivos.most_common()))

    # Mais recentes primeiro; aplica o teto por execução (o resto vai na próxima).
    aceitas.sort(key=lambda par: par[0].publicada_em, reverse=True)
    if len(aceitas) > cfg.max_vagas_por_execucao:
        log.info("Limitando a %d vagas nesta execução (de %d)", cfg.max_vagas_por_execucao, len(aceitas))
        aceitas = aceitas[: cfg.max_vagas_por_execucao]

    if not aceitas:
        log.info("Nenhuma vaga nova.")
        if not isinstance(notificador, Console):
            estado_mod.salvar(estado, cfg.caminho_estado)  # grava a poda
        return 0

    grupos = montar_mensagens(aceitas, cfg.vagas_por_mensagem)
    enviadas = 0
    try:
        for i, grupo in enumerate(grupos, start=1):
            notificador.enviar(texto_do_grupo(grupo, i, len(grupos)))
            # Só marca como enviada DEPOIS do envio dar certo.
            for vaga, _ in grupo:
                estado[vaga.chave] = agora.isoformat()
                enviadas += 1
    finally:
        # Mesmo se um envio falhar no meio, salva o que já foi enviado,
        # para não repetir essas vagas na próxima execução.
        if not isinstance(notificador, Console):
            estado_mod.salvar(estado, cfg.caminho_estado)
    modo = " (dry-run, nada foi enviado)" if isinstance(notificador, Console) else ""
    log.info("%d vagas em %d mensagens%s", enviadas, len(grupos), modo)
    return enviadas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Busca vagas remotas de dados e envia pelo WhatsApp")
    parser.add_argument("--dry-run", action="store_true", help="imprime as mensagens em vez de enviar e não altera o estado")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = Config.do_ambiente()
    try:
        notificador: Notificador = Console() if args.dry_run else CallMeBot.do_ambiente()
        executar(cfg, notificador)
    except (gupy.ErroFonte, ErroEnvio) as e:
        # Código de saída != 0 faz o GitHub Actions marcar a execução como falha
        # e mandar e-mail para você: é o nosso "alarme".
        log.error("Execução falhou: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
