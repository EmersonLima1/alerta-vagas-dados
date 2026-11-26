"""Fonte: API pública do portal de vagas da Gupy.

A Gupy é a maior plataforma de recrutamento do Brasil e o portal
(portal.gupy.io) consome uma API pública, sem autenticação, que lista
vagas de todas as empresas. Usamos essa API em vez de raspar HTML:
é mais estável, mais leve e não exige contornar nada.

ATENÇÃO: a API não é documentada oficialmente. O formato abaixo é o
observado publicamente; se a Gupy mudar algo, `normalizar` vai acusar
erro e o workflow falha (você recebe e-mail do GitHub), em vez de
silenciosamente parar de enviar vagas.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

import requests

from ..modelos import Vaga

log = logging.getLogger(__name__)

URL_API = "https://portal.api.gupy.io/api/v1/jobs"
LIMITE_POR_PAGINA = 100
MAX_PAGINAS = 5  # trava de segurança contra loop infinito de paginação
TIMEOUT_S = 20
TENTATIVAS = 3

# Assinatura de uma função que faz GET e devolve o JSON. Injetável para testes.
Buscador = Callable[[str, dict[str, Any]], dict[str, Any]]


class ErroFonte(RuntimeError):
    """Falha ao consultar ou interpretar a fonte."""


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET com nova tentativa em erros temporários (rede, 429, 5xx)."""
    ultimo_erro: Exception | None = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resp = requests.get(
                url,
                params=params,
                timeout=TIMEOUT_S,
                headers={"User-Agent": "alerta-vagas-dados/1.0", "Accept": "application/json"},
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                raise ErroFonte(f"HTTP {resp.status_code}")
            resp.raise_for_status()  # 4xx (exceto 429) não adianta repetir
            return resp.json()
        except requests.HTTPError as e:
            raise ErroFonte(f"Gupy respondeu {e.response.status_code}: {e}") from e
        except (requests.RequestException, ErroFonte, ValueError) as e:
            ultimo_erro = e
            log.warning("Gupy: tentativa %d/%d falhou: %s", tentativa, TENTATIVAS, e)
            time.sleep(2 ** tentativa)  # espera 2s, 4s, 8s (backoff exponencial)
    raise ErroFonte(f"Gupy indisponível após {TENTATIVAS} tentativas: {ultimo_erro}")


def _parse_data(valor: str | None) -> datetime | None:
    if not valor:
        return None
    # A API devolve ISO 8601 com "Z" no fim (ex.: 2026-11-20T13:45:00.000Z)
    dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def normalizar(item: dict[str, Any]) -> Vaga:
    """Converte um item da API da Gupy para `Vaga`.

    Campos obrigatórios ausentes geram KeyError de propósito (mudança de
    formato da API deve ser percebida, não ignorada).
    """
    workplace = (item.get("workplaceType") or "").lower()
    return Vaga(
        fonte="gupy",
        id_fonte=str(item["id"]),
        titulo=item["name"].strip(),
        empresa=(item.get("careerPageName") or "").strip(),
        url=item["jobUrl"],
        publicada_em=_parse_data(item.get("publishedDate")),
        remota=workplace == "remote" or bool(item.get("isRemoteWork")),
        pais=(item.get("country") or "").strip(),
        cidade=(item.get("city") or "").strip(),
        estado=(item.get("state") or "").strip(),
    )


def buscar(termos: Iterable[str], get_json: Buscador = _get_json) -> list[Vaga]:
    """Busca vagas remotas para cada termo, com paginação, sem duplicar ids."""
    vistas: dict[str, Vaga] = {}
    erros = 0
    termos = list(termos)
    for termo in termos:
        try:
            for pagina in range(MAX_PAGINAS):
                params = {
                    "jobName": termo,
                    "workplaceType": "remote",
                    "limit": LIMITE_POR_PAGINA,
                    "offset": pagina * LIMITE_POR_PAGINA,
                }
                dados = get_json(URL_API, params)
                itens = dados.get("data")
                if not isinstance(itens, list):
                    raise ErroFonte(f"resposta sem lista 'data' (chaves: {list(dados)})")
                for item in itens:
                    vaga = normalizar(item)
                    vistas.setdefault(vaga.chave, vaga)
                if len(itens) < LIMITE_POR_PAGINA:
                    break
        except (ErroFonte, KeyError, TypeError, ValueError) as e:
            # Um termo com problema não derruba os outros...
            erros += 1
            log.error("Gupy: falha no termo %r: %r", termo, e)
    if termos and erros == len(termos):
        # ...mas se TODOS falharam, algo está errado com a fonte.
        raise ErroFonte("todas as buscas na Gupy falharam")
    log.info("Gupy: %d vagas únicas encontradas (%d termos)", len(vistas), len(termos))
    return list(vistas.values())
