"""Regressões e recursos da versão 0.2.0."""
import json

import pytest

from vbp import approval, publish
from vbp.assets import check_licenses
from vbp.config import ROOT
from vbp.media import make_images, make_narration, spoken_for_tts
from vbp.obs import StageResult
from vbp.script import failed, validate_script
from vbp.state import State

from conftest import SpyProvider


def _board(texto="Davi chegou ao vale."):
    return {"cenas": [{"id": 1, "texto": texto, "plano": "wide", "seed": 1, "prompt_imagem": texto,
                       "referencias": ["1 Samuel 17:1"]}]}


def test_arquivos_necessarios_existem():
    assert (ROOT / ".env.example").exists() and (ROOT / ".gitignore").exists()


def test_audio_e_imagem_velhos_sao_refeitos(cfg, tmp_path):
    for make in (make_narration, make_images):
        assert make(_board(), tmp_path, cfg)["geradas"] == 1
        assert make(_board(), tmp_path, cfg)["reaproveitadas"] == 1
        assert make(_board("Texto totalmente novo depois do ajuste."), tmp_path, cfg)["geradas"] == 1
    assert list((tmp_path / "audio" / "_antigos").iterdir())  # arquivado, não apagado


def test_arquivo_externo_velho_bloqueia_e_novo_e_aceito(cfg, tmp_path):
    cfg["imagens"]["provedor"] = "externo"
    (tmp_path / "imagens").mkdir()
    img = tmp_path / "imagens" / "cena_001.png"
    img.write_bytes(b"primeira")
    assert make_images(_board(), tmp_path, cfg)["reaproveitadas"] == 1
    with pytest.raises(StageResult):
        make_images(_board("outro texto"), tmp_path, cfg)
    img.write_bytes(b"segunda")
    assert make_images(_board("outro texto"), tmp_path, cfg)["reaproveitadas"] == 1


def test_pronuncia_vai_so_para_a_voz(cfg, tmp_path):
    scene = {"texto": "No vale de Elá, Elátrio esperava."}
    assert spoken_for_tts(scene, {"Elá": "Elah"}) == "No vale de Elah, Elátrio esperava."
    assert spoken_for_tts({**scene, "pronuncia": "outra fala"}, {}) == "outra fala"
    cfg["pronuncia"] = {"Davi": "Daví"}
    board = _board()
    make_narration(board, tmp_path, cfg)
    assert "Daví" in (tmp_path / "audio" / "textos.json").read_text(encoding="utf-8")
    assert board["cenas"][0]["texto"] == "Davi chegou ao vale."  # legenda intacta


def test_licencas_e_descricao(cfg, tmp_path):
    cfg["imagens"]["provedor"] = "externo"
    (tmp_path / "imagens").mkdir()
    (tmp_path / "imagens" / "cena_001.png").write_bytes(b"x")
    make_images(_board(), tmp_path, cfg)
    assert check_licenses(tmp_path)[0]
    csv = tmp_path / "licencas.csv"
    csv.write_text("arquivo,autor,licenca,origem\nimagens/*,Fulana,CC BY-NC 4.0,\n", encoding="utf-8")
    assert "proíbe" in check_licenses(tmp_path)[0][0]
    csv.write_text("arquivo,autor,licenca,origem\nimagens/*,Fulana,CC BY 4.0,https://exemplo.org\n", encoding="utf-8")
    problems, credits = check_licenses(tmp_path)
    assert problems == [] and credits == ["Fulana (CC BY 4.0) https://exemplo.org"]
    (tmp_path / "storyboard.json").write_text(json.dumps(_board()), encoding="utf-8")
    desc = publish.build_description(tmp_path, "a" * 6000, credits)
    assert len(desc) <= 4900 and "1 Samuel 17:1" in desc and "Fulana" in desc


@pytest.mark.parametrize("value", ["amanhã", "2020-01-01T10:00:00Z", "2099-01-01T10:00:00"])
def test_agendamento_invalido(value):
    with pytest.raises(StageResult):
        publish.normalize_publish_at(value)


def test_agendamento_converte_para_utc():
    assert publish.normalize_publish_at("2099-01-01T18:00:00-03:00") == "2099-01-01T21:00:00Z"


def test_nao_envia_duas_vezes(make_pipeline, episode, monkeypatch):
    p = make_pipeline(live=True)
    p.state.add_episode(*episode)
    p.run("EP001")
    approval.approve(p.state, "EP001", p.ep_dir("EP001"), "Revisor")
    calls = []

    def fake_publish(ep_dir, cfg, live, publish_at=None, on_uploaded=None):
        calls.append(1)
        on_uploaded("abc123")
        raise RuntimeError("thumbnail recusada")  # falha depois do envio

    monkeypatch.setattr(publish, "publish", fake_publish)
    make_pipeline(live=True).run("EP001")
    summary = make_pipeline(live=True).run("EP001")
    assert len(calls) == 1
    assert summary["stages"][-1]["status"] == "SKIPPED"
    assert p.state.episode("EP001")["status"] == "PUBLICADO"


def test_resposta_reprovada_nao_fica_no_cache(make_pipeline, episode):
    ruim = SpyProvider(lambda prompt: json.dumps({"titulo": "x", "secoes": []}))
    p = make_pipeline(providers=[ruim])
    p.state.add_episode(*episode)
    p.run("EP001")
    make_pipeline(providers=[ruim]).run("EP001")
    assert len(ruim.prompts) == 4


@pytest.mark.parametrize("bad", [{"secoes": ["texto solto"]}, {"secoes": "x"}, {"gancho": ["a"]}])
def test_formato_errado_do_llm_nao_quebra(cfg, bad):
    assert [c["check"] for c in failed(validate_script(bad, cfg))] == ["formato_json"]


def test_tema_repetido(tmp_path):
    st = State(tmp_path / "s.db")
    st.add_episode("E1", "Davi e Golias", "t", "1 Samuel 17:4; Salmos 23")
    assert st.find_duplicate("DAVI E GOLIAS!", "João 3:16") == "E1"
    assert st.find_duplicate("Outro título", "salmos 23; 1 samuel 17:4") == "E1"
    assert st.find_duplicate("Rute", "Rute 1:1") is None


def test_telegram_ignora_episodio_desconhecido(tmp_path, monkeypatch):
    st = State(tmp_path / "s.db")
    tg = approval.Telegram("t", {1})
    updates = [{"update_id": i, "message": {"chat": {"id": 1}, "text": t}}
               for i, t in enumerate(["/aprovar ../../x", "/ajustar EP9 motivo"])]
    monkeypatch.setattr(tg, "_call", lambda *a: {"result": updates})
    assert all("desconhecido" in h for h in tg.poll_once(st, tmp_path))
    assert st.latest_approval("EP9") is None
