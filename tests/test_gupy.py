import pytest

from alerta_vagas.fontes import gupy


def item(id_, nome="Analista de Dados Jr", **extra):
    base = {
        "id": id_, "name": nome, "careerPageName": "ACME", "jobUrl": f"https://acme.gupy.io/jobs/{id_}",
        "publishedDate": "2026-11-25T10:00:00.000Z", "workplaceType": "remote",
        "isRemoteWork": True, "country": "Brasil", "city": "", "state": "",
    }
    base.update(extra)
    return base


def test_normalizar_converte_campos():
    v = gupy.normalizar(item(42))
    assert v.chave == "gupy:42"
    assert v.remota is True
    assert v.publicada_em.isoformat() == "2026-11-25T10:00:00+00:00"


def test_normalizar_falha_se_formato_mudar():
    with pytest.raises(KeyError):
        gupy.normalizar({"id": 1})  # sem "name"/"jobUrl"


def test_buscar_pagina_e_remove_duplicadas(monkeypatch):
    monkeypatch.setattr(gupy, "LIMITE_POR_PAGINA", 2)
    chamadas = []

    def falso_get(url, params):
        chamadas.append(params)
        if params["jobName"] == "a":
            paginas = {0: [item(1), item(2)], 2: [item(3)]}
            return {"data": paginas[params["offset"]]}
        return {"data": [item(1)]}  # mesma vaga aparece em outro termo

    vagas = gupy.buscar(["a", "b"], get_json=falso_get)
    assert sorted(v.id_fonte for v in vagas) == ["1", "2", "3"]
    assert len(chamadas) == 3
    assert all(c["workplaceType"] == "remote" for c in chamadas)


def test_um_termo_falhando_nao_derruba_os_outros():
    def falso_get(url, params):
        if params["jobName"] == "ruim":
            raise gupy.ErroFonte("HTTP 500")
        return {"data": [item(1)]}

    assert len(gupy.buscar(["ruim", "bom"], get_json=falso_get)) == 1


def test_todos_os_termos_falhando_gera_erro():
    def falso_get(url, params):
        return {"erro": "formato novo"}

    with pytest.raises(gupy.ErroFonte):
        gupy.buscar(["a", "b"], get_json=falso_get)
