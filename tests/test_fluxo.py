"""Testes do fluxo completo, com fonte e WhatsApp falsos."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from alerta_vagas.__main__ import executar
from alerta_vagas.config import Config
from alerta_vagas.modelos import Vaga
from alerta_vagas.notificador import ErroEnvio

AGORA = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


def v(id_, titulo="Analista de Dados Jr", dias=1):
    return Vaga("gupy", str(id_), titulo, "ACME", f"https://x/{id_}", AGORA - timedelta(days=dias), True, "Brasil")


class WhatsAppFalso:
    def __init__(self, falhar_na=None):
        self.mensagens, self.falhar_na = [], falhar_na

    def enviar(self, texto):
        if self.falhar_na is not None and len(self.mensagens) == self.falhar_na:
            raise ErroEnvio("simulado")
        self.mensagens.append(texto)


@pytest.fixture
def cfg(tmp_path):
    return Config(caminho_estado=str(tmp_path / "estado.json"), vagas_por_mensagem=2)


def test_envia_apenas_vagas_validas_e_nao_repete(cfg):
    vagas = [v(1), v(2, "Analista de Dados Sênior"), v(3, dias=30), v(4, "Cientista de Dados Jr")]
    zap = WhatsAppFalso()

    assert executar(cfg, zap, buscar=lambda _: vagas, agora=AGORA) == 2
    assert len(zap.mensagens) == 1
    assert "https://x/1" in zap.mensagens[0] and "https://x/4" in zap.mensagens[0]

    # Segunda execução com as mesmas vagas: nada novo.
    zap2 = WhatsAppFalso()
    assert executar(cfg, zap2, buscar=lambda _: vagas, agora=AGORA) == 0
    assert zap2.mensagens == []


def test_falha_no_meio_salva_so_o_que_foi_enviado(cfg):
    vagas = [v(i) for i in range(1, 5)]  # 4 vagas -> 2 mensagens de 2
    with pytest.raises(ErroEnvio):
        executar(cfg, WhatsAppFalso(falhar_na=1), buscar=lambda _: vagas, agora=AGORA)
    estado = json.loads(open(cfg.caminho_estado).read())
    assert len(estado) == 2  # só a 1ª mensagem saiu

    # Próxima execução envia só as 2 que faltaram.
    zap = WhatsAppFalso()
    assert executar(cfg, zap, buscar=lambda _: vagas, agora=AGORA) == 2


def test_teto_por_execucao_prioriza_mais_recentes(cfg):
    cfg.max_vagas_por_execucao = 2
    vagas = [v(1, dias=5), v(2, dias=1), v(3, dias=3)]
    zap = WhatsAppFalso()
    executar(cfg, zap, buscar=lambda _: vagas, agora=AGORA)
    assert "https://x/2" in zap.mensagens[0] and "https://x/3" in zap.mensagens[0]
    assert "https://x/1" not in zap.mensagens[0]


def test_estado_antigo_e_podado(cfg):
    antigo = (AGORA - timedelta(days=90)).isoformat()
    with open(cfg.caminho_estado, "w") as f:
        json.dump({"gupy:velha": antigo}, f)
    executar(cfg, WhatsAppFalso(), buscar=lambda _: [], agora=AGORA)
    assert json.loads(open(cfg.caminho_estado).read()) == {}
