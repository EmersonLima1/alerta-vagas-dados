from datetime import datetime, timedelta, timezone

import pytest

from alerta_vagas.config import Config
from alerta_vagas.filtros import avaliar, identificar_cargo, identificar_nivel
from alerta_vagas.modelos import Vaga

AGORA = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


def vaga(titulo="Analista de Dados Jr", dias=1, remota=True, pais="Brasil", **kw):
    return Vaga(
        fonte="gupy", id_fonte=kw.pop("id_fonte", "1"), titulo=titulo, empresa="ACME",
        url="https://acme.gupy.io/jobs/1", publicada_em=AGORA - timedelta(days=dias),
        remota=remota, pais=pais, **kw,
    )


@pytest.mark.parametrize("titulo, nivel", [
    ("Analista de Dados Júnior", "junior"),
    ("Analista de Dados Jr.", "junior"),
    ("Analista de Dados I", "junior"),
    ("Analista de Dados II", "pleno"),
    ("Analista de Dados III", "senior"),
    ("Analista de Dados Pleno", "pleno"),
    ("Analista de Dados Sênior", "senior"),
    ("Analista de Dados Sr", "senior"),
    ("Especialista em Dados", "senior"),
    ("Estágio em Análise de Dados", "estagio"),
    ("Analista de Dados", "nao_informado"),
    ("Analista de BI", "nao_informado"),  # "BI" não pode virar nível "I"
])
def test_identificar_nivel(titulo, nivel):
    assert identificar_nivel(titulo) == nivel


@pytest.mark.parametrize("titulo, cargo", [
    ("Analista de Dados Jr", "Analista de Dados"),
    ("Data Analyst Junior", "Analista de Dados"),
    ("Analista de BI Pleno", "Analista de BI"),
    ("Analista de Business Intelligence", "Analista de BI"),
    ("Cientista de Dados Júnior", "Cientista de Dados"),
    ("Engenheira de Dados Jr", "Engenheiro de Dados"),
    ("Engenharia de Dados - Júnior", "Engenheiro de Dados"),
    ("Desenvolvedor Python", None),
    ("Analista de Sistemas", None),
])
def test_identificar_cargo(titulo, cargo):
    assert identificar_cargo(titulo) == cargo


@pytest.mark.parametrize("titulo, esperado", [
    ("Analista de Dados Jr", True),
    ("Analista de Dados Pleno", True),
    ("Analista de Dados Sênior", False),
    ("Analista de BI Pleno", True),
    ("Cientista de Dados Júnior", True),
    ("Cientista de Dados Pleno", False),   # cientista: só júnior
    ("Engenheiro de Dados Jr", True),
    ("Engenheiro de Dados Pleno", False),  # engenheiro: só júnior
    ("Estágio em Dados", False),
    ("Analista de Dados", True),           # nível não informado: aceito por padrão
])
def test_avaliar_cargo_e_nivel(titulo, esperado):
    ok, _ = avaliar(vaga(titulo), Config(), AGORA)
    assert ok is esperado


def test_nivel_nao_informado_pode_ser_recusado():
    cfg = Config(aceitar_nivel_nao_informado=False)
    assert avaliar(vaga("Analista de Dados"), cfg, AGORA)[0] is False


def test_recusa_nao_remota():
    assert avaliar(vaga(remota=False), Config(), AGORA) == (False, "nao_remota")


@pytest.mark.parametrize("pais, titulo, esperado", [
    ("Brasil", "Analista de Dados Jr", True),
    ("Brazil", "Analista de Dados Jr", True),
    ("", "Analista de Dados Jr", True),
    ("Portugal", "Analista de Dados Jr", False),
    ("Brasil", "Data Analyst Jr - International", False),
    ("Brasil", "Analista de Dados Jr (LATAM)", False),
])
def test_somente_brasil(pais, titulo, esperado):
    assert avaliar(vaga(titulo, pais=pais), Config(), AGORA)[0] is esperado


def test_idade_maxima():
    cfg = Config(max_dias=7)
    assert avaliar(vaga(dias=6.9), cfg, AGORA)[0] is True
    assert avaliar(vaga(dias=7.1), cfg, AGORA) == (False, "antiga_ou_sem_data")


def test_sem_data_e_recusada():
    v = Vaga("gupy", "1", "Analista de Dados Jr", "ACME", "u", None, True, "Brasil")
    assert avaliar(v, Config(), AGORA) == (False, "antiga_ou_sem_data")
