"""Envio das mensagens: Telegram (padrão) ou WhatsApp via CallMeBot.

- Telegram: API oficial e gratuita de bots. Você cria um bot com o
  @BotFather, recebe um token e envia com POST em /sendMessage.
- CallMeBot: serviço gratuito e não oficial de WhatsApp para uso pessoal
  (em nov/2026 estava sem vagas para novos usuários).

Qual canal usar é decidido pelos secrets presentes (ver `do_ambiente`),
então trocar de canal não exige mudar código. Credenciais vêm sempre de
variáveis de ambiente (GitHub Secrets no Actions), nunca do código.
"""

from __future__ import annotations

import html
import logging
import os
import re
import time
from typing import Protocol

import requests

from .modelos import Vaga

log = logging.getLogger(__name__)

URL_CALLMEBOT = "https://api.callmebot.com/whatsapp.php"
LIMITE_CARACTERES = 1500  # margem segura para o tamanho da URL do GET
PAUSA_ENTRE_ENVIOS_S = 5  # o CallMeBot recomenda não disparar em rajada


class ErroEnvio(RuntimeError):
    pass


class Notificador(Protocol):
    def enviar(self, texto: str) -> None: ...


class CallMeBot:
    def __init__(self, telefone: str, apikey: str, pausa_s: float = PAUSA_ENTRE_ENVIOS_S):
        if not telefone or not apikey:
            raise ErroEnvio("WHATSAPP_PHONE e CALLMEBOT_APIKEY precisam estar definidos")
        self.telefone = telefone
        self.apikey = apikey
        self.pausa_s = pausa_s
        self._enviadas = 0

    @classmethod
    def do_ambiente(cls) -> "CallMeBot":
        return cls(os.getenv("WHATSAPP_PHONE", ""), os.getenv("CALLMEBOT_APIKEY", ""))

    def enviar(self, texto: str) -> None:
        if self._enviadas:
            time.sleep(self.pausa_s)
        try:
            resp = requests.get(
                URL_CALLMEBOT,
                params={"phone": self.telefone, "text": texto, "apikey": self.apikey},
                timeout=30,
            )
        except requests.RequestException as e:
            # Não logamos a URL: ela contém a apikey.
            raise ErroEnvio(f"falha de rede ao chamar o CallMeBot: {type(e).__name__}") from None
        corpo = resp.text.lower()
        # O CallMeBot às vezes responde 200 com mensagem de erro no HTML.
        if resp.status_code != 200 or "error" in corpo or "apikey is invalid" in corpo:
            raise ErroEnvio(f"CallMeBot recusou o envio (HTTP {resp.status_code}): {resp.text[:200]}")
        self._enviadas += 1


URL_TELEGRAM = "https://api.telegram.org/bot{token}/sendMessage"


class Telegram:
    def __init__(self, token: str, chat_id: str, pausa_s: float = 1):
        if not token or not chat_id:
            raise ErroEnvio("TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID precisam estar definidos")
        self.token = token
        self.chat_id = chat_id
        self.pausa_s = pausa_s
        self._enviadas = 0

    @staticmethod
    def para_html(texto: str) -> str:
        """Converte o *negrito* estilo WhatsApp para HTML do Telegram.
        Escapamos o texto antes: um título com '<' ou '&' quebraria o envio."""
        return re.sub(r"\*([^*\n]+)\*", r"<b>\1</b>", html.escape(texto, quote=False))

    def enviar(self, texto: str) -> None:
        if self._enviadas:
            time.sleep(self.pausa_s)
        try:
            resp = requests.post(
                URL_TELEGRAM.format(token=self.token),
                json={
                    "chat_id": self.chat_id,
                    "text": self.para_html(texto),
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=30,
            )
        except requests.RequestException as e:
            # Não logamos a URL: ela contém o token do bot.
            raise ErroEnvio(f"falha de rede ao chamar o Telegram: {type(e).__name__}") from None
        try:
            corpo = resp.json()
        except ValueError:
            corpo = {}
        if resp.status_code != 200 or not corpo.get("ok"):
            descricao = corpo.get("description", resp.text[:200]).replace(self.token, "***")
            raise ErroEnvio(f"Telegram recusou o envio (HTTP {resp.status_code}): {descricao}")
        self._enviadas += 1


def do_ambiente() -> Notificador:
    """Escolhe o canal pelos secrets definidos: Telegram tem prioridade."""
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        log.info("Canal de envio: Telegram")
        return Telegram(os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", ""))
    if os.getenv("CALLMEBOT_APIKEY"):
        log.info("Canal de envio: WhatsApp (CallMeBot)")
        return CallMeBot.do_ambiente()
    raise ErroEnvio(
        "Nenhum canal configurado: defina TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID "
        "ou WHATSAPP_PHONE e CALLMEBOT_APIKEY"
    )


class Console:
    """Modo de teste (dry-run): imprime em vez de enviar."""

    def enviar(self, texto: str) -> None:
        print("----- mensagem (dry-run) -----")
        print(texto)


def formatar_vaga(vaga: Vaga, motivo: str) -> str:
    data = vaga.publicada_em.strftime("%d/%m") if vaga.publicada_em else "?"
    nivel = motivo.split("/", 1)[1] if "/" in motivo else ""
    nivel_txt = {"junior": "Jr", "pleno": "Pleno", "nivel_nao_informado": "nível não informado"}.get(nivel, nivel)
    empresa = f" — {vaga.empresa}" if vaga.empresa else ""
    return f"• *{vaga.titulo}*{empresa}\n  {nivel_txt} · publicada {data}\n  {vaga.url}"


def montar_mensagens(itens: list[tuple[Vaga, str]], por_mensagem: int) -> list[list[tuple[Vaga, str]]]:
    """Agrupa as vagas em blocos, respeitando quantidade e tamanho máximo."""
    grupos: list[list[tuple[Vaga, str]]] = []
    atual: list[tuple[Vaga, str]] = []
    tamanho = 0
    for vaga, motivo in itens:
        bloco = len(formatar_vaga(vaga, motivo)) + 2
        if atual and (len(atual) >= por_mensagem or tamanho + bloco > LIMITE_CARACTERES):
            grupos.append(atual)
            atual, tamanho = [], 0
        atual.append((vaga, motivo))
        tamanho += bloco
    if atual:
        grupos.append(atual)
    return grupos


def texto_do_grupo(grupo: list[tuple[Vaga, str]], indice: int, total: int) -> str:
    cabecalho = f"🔎 *Novas vagas remotas de dados* ({indice}/{total})"
    return cabecalho + "\n\n" + "\n\n".join(formatar_vaga(v, m) for v, m in grupo)
