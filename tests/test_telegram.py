import pytest

from alerta_vagas import notificador
from alerta_vagas.notificador import CallMeBot, ErroEnvio, Telegram


class Resp:
    def __init__(self, status, corpo):
        self.status_code, self._corpo, self.text = status, corpo, str(corpo)

    def json(self):
        return self._corpo


def test_converte_negrito_e_escapa_html():
    assert Telegram.para_html("*Dados & BI <Jr>*") == "<b>Dados &amp; BI &lt;Jr&gt;</b>"


def test_envio_ok(monkeypatch):
    enviados = []
    monkeypatch.setattr("requests.post", lambda url, json, timeout: enviados.append(json) or Resp(200, {"ok": True}))
    Telegram("TOKEN", "123", pausa_s=0).enviar("*Vaga*")
    assert enviados[0]["parse_mode"] == "HTML" and enviados[0]["text"] == "<b>Vaga</b>"


def test_erro_nao_vaza_token(monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: Resp(401, {"ok": False, "description": "Unauthorized for bot TOKENSECRETO"}),
    )
    with pytest.raises(ErroEnvio) as e:
        Telegram("TOKENSECRETO", "123", pausa_s=0).enviar("oi")
    assert "TOKENSECRETO" not in str(e.value)


def test_escolha_do_canal(monkeypatch):
    for v in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "CALLMEBOT_APIKEY", "WHATSAPP_PHONE"]:
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(ErroEnvio):
        notificador.do_ambiente()

    monkeypatch.setenv("CALLMEBOT_APIKEY", "k")
    monkeypatch.setenv("WHATSAPP_PHONE", "+55")
    assert isinstance(notificador.do_ambiente(), CallMeBot)

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    assert isinstance(notificador.do_ambiente(), Telegram)
