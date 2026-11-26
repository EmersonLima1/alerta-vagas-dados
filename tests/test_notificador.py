import pytest

from alerta_vagas.notificador import CallMeBot, ErroEnvio


class Resp:
    def __init__(self, status, text):
        self.status_code, self.text = status, text


def test_exige_credenciais():
    with pytest.raises(ErroEnvio):
        CallMeBot("", "")


def test_sucesso(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **k: Resp(200, "Message queued. You will receive it in a few seconds."))
    CallMeBot("+5577999999999", "123", pausa_s=0).enviar("oi")


def test_erro_em_resposta_200_e_detectado(monkeypatch):
    # O CallMeBot pode responder 200 com erro no corpo.
    monkeypatch.setattr("requests.get", lambda *a, **k: Resp(200, "APIKey is invalid"))
    with pytest.raises(ErroEnvio):
        CallMeBot("+5577999999999", "123", pausa_s=0).enviar("oi")


def test_erro_de_rede_nao_vaza_apikey(monkeypatch):
    import requests

    def explode(*a, **k):
        raise requests.ConnectionError("https://api.callmebot.com/...apikey=SEGREDO")

    monkeypatch.setattr("requests.get", explode)
    with pytest.raises(ErroEnvio) as e:
        CallMeBot("+5577999999999", "SEGREDO", pausa_s=0).enviar("oi")
    assert "SEGREDO" not in str(e.value)
