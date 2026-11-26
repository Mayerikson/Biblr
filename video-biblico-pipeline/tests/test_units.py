import json
import sqlite3

import pytest

from vbp.bible_refs import find_refs, parse_ref
from vbp.budget import Budget, BudgetExceeded
from vbp.demo import responder
from vbp.llm import FakeProvider, LLMClient, LLMError, extract_json
from vbp.media import build_srt
from vbp.obs import Observer, StageResult, redact
from vbp.script import spoken_text, validate_script, failed
from vbp.state import State
from vbp.storyboard import apply_llm_descriptions, build_storyboard, choose_shot


# ---------------------------------------------------------------- referências (TU-01)
@pytest.mark.parametrize("text,expected", [
    ("1 Samuel 17:45", "1 Samuel 17:45"), ("1Sm 17.4-7", "1 Samuel 17:4-7"), ("Sl 23", "Salmos 23"),
    ("Jó 1:1", "Jó 1:1"), ("Jo 3:16", "João 3:16"), ("Cântico dos Cânticos 2:1", "Cantares 2:1"),
])
def test_refs_validas(text, expected):
    ref, why = parse_ref(text)
    assert ref is not None, why
    assert str(ref) == expected


@pytest.mark.parametrize("text", ["Golias 3:1", "Judas 2", "Salmos 151", "Ex 3:14-12"])
def test_refs_invalidas(text):
    ref, why = parse_ref(text)
    assert ref is None and why


def test_find_refs_so_entre_parenteses():
    assert find_refs("Davi (1 Samuel 17:45) e (veja nota) e (Sl 23)") == ["1 Samuel 17:45", "Sl 23"]


# ---------------------------------------------------------------- roteiro (TU-02)
def _demo_script(cfg):
    from vbp.script import build_prompt
    ep = {"id": "EP1", "titulo": "Teste", "tema": "t", "referencias": "1 Samuel 17:45", "personagens": ""}
    return json.loads(responder(build_prompt(ep, cfg)))


def test_roteiro_demo_passa(cfg):
    assert failed(validate_script(_demo_script(cfg), cfg)) == []


def test_roteiro_reprova_isca(cfg):
    s = _demo_script(cfg)
    s["gancho"] = "Não pule este vídeo! " + s["gancho"]
    assert "sem_isca_ou_direcao_de_cena" in [c["check"] for c in failed(validate_script(s, cfg))]


def test_roteiro_reprova_secao_sem_referencia_e_ref_invalida(cfg):
    s = _demo_script(cfg)
    s["secoes"][0]["texto"] = "Texto sem referência alguma."
    s["secoes"][1]["texto"] += " (Golias 3:1)"
    bad = {c["check"] for c in failed(validate_script(s, cfg))}
    assert {"referencia_por_secao", "referencias_validas"} <= bad


def test_roteiro_reprova_quantidade_de_secoes(cfg):
    s = _demo_script(cfg)
    s["secoes"] = s["secoes"][:2]
    assert "quantidade_secoes" in [c["check"] for c in failed(validate_script(s, cfg))]


def test_spoken_text_remove_referencias():
    clean, refs = spoken_text("Davi falou (1 Samuel 17:45). Depois venceu (1 Samuel 17:50).")
    assert clean == "Davi falou. Depois venceu."
    assert refs == ["1 Samuel 17:45", "1 Samuel 17:50"]


# ---------------------------------------------------------------- storyboard (TU-03)
def test_regra_de_plano_e_explicacao():
    c = choose_shot("O gigante gritou contra Israel", [], False)
    assert c["shot"] == "low_angle" and c["matched"] == "gigante"


def test_restricao_de_variedade():
    c = choose_shot("O rei e o exército", ["low_angle", "low_angle"], False)
    assert c["shot"] != "low_angle"


def test_personagem_e_seed_fixos(cfg):
    script = {"titulo": "t", "texto_thumbnail": "X", "gancho": "Davi chegou ao vale (1 Samuel 17:1).",
              "secoes": [], "conclusao": ""}
    board, explain = build_storyboard(script, cfg)
    sc = board["cenas"][0]
    assert sc["personagens"][0]["id"] == "davi" and sc["seed"] == 1017
    assert "jovem pastor" in sc["prompt_imagem"]
    assert "(1 Samuel" not in sc["texto"] and sc["referencias"] == ["1 Samuel 17:1"]
    assert explain["decisoes"][0]["regra"]


def test_llm_nao_muda_plano(cfg):
    script = {"titulo": "t", "texto_thumbnail": "X", "gancho": "O gigante avançou (1 Samuel 17:4).",
              "secoes": [], "conclusao": ""}
    board, _ = build_storyboard(script, cfg)
    antes = board["cenas"][0]["plano"]
    apply_llm_descriptions(board, {"cenas": [{"id": 1, "descricao": "nova", "plano": "wide"}]}, "estilo")
    assert board["cenas"][0]["plano"] == antes and board["cenas"][0]["descricao"] == "nova"


# ---------------------------------------------------------------- LLM (TU-04)
def test_extract_json_variantes():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('blá blá {"a": {"b": "}"}} fim') == {"a": {"b": "}"}}
    with pytest.raises(LLMError):
        extract_json("sem json")


def _client(tmp_path, providers, budget=None):
    obs = Observer(tmp_path / "runs", echo=False)
    return LLMClient(providers, State(tmp_path / "s.db"), obs, budget or Budget()), obs


def test_fallback_circuit_breaker_e_cache(tmp_path):
    calls = {"ruim": 0, "bom": 0}

    def ruim(p):
        calls["ruim"] += 1
        raise LLMError("fora do ar")

    def bom(p):
        calls["bom"] += 1
        return '{"ok": true}'

    client, obs = _client(tmp_path, [FakeProvider(ruim, "ruim"), FakeProvider(bom, "bom")])
    assert client.json("p1", temperature=0, stage="T")[0] == {"ok": True}
    assert client.json("p2", temperature=0, stage="T")[0] == {"ok": True}
    assert calls == {"ruim": 1, "bom": 2}  # provedor quebrado não é chamado de novo
    data, prov = client.json("p1", temperature=0, stage="T")
    assert prov["cache"] is True and calls["bom"] == 2
    assert obs.metrics["fallbacks"] == 1 and obs.metrics["llm_cache_hits"] == 1


def test_orcamento_bloqueia_antes_da_chamada(tmp_path):
    chamado = []
    client, _ = _client(tmp_path, [FakeProvider(lambda p: chamado.append(p) or "{}")], Budget(max_llm_calls=0))
    with pytest.raises(BudgetExceeded):
        client.json("x", temperature=0, stage="T")
    assert chamado == []


# ---------------------------------------------------------------- estado e observabilidade (TU-05)
def test_eventos_append_only_e_idempotencia(tmp_path):
    st = State(tmp_path / "s.db")
    assert st.add_episode("E1", "t", "t", "Sl 23") is True
    assert st.add_episode("E1", "outro", "t", "Sl 23") is False
    st.append_event({"ts": "x", "event": "e"})
    with st.conn() as c, pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE events SET event='hack'")
    with st.conn() as c, pytest.raises(sqlite3.IntegrityError):
        c.execute("DELETE FROM events")


def test_redact_remove_segredos():
    out = redact({"api_key": "abc", "msg": "chave AIzaSyD4f8s7d6f5g4h3j2k1l0qwertyui no texto", "ok": "x"})
    assert out["api_key"] == "***" and "AIza" not in out["msg"] and out["ok"] == "x"


def test_span_registra_status_e_resumo(tmp_path):
    obs = Observer(tmp_path, echo=False)
    with obs.span("A", "E1"):
        pass
    with obs.span("B", "E1"):
        raise StageResult("BLOCKED", "gate")
    with obs.span("C", "E1"):
        raise ValueError("token sk-abcdefghijklmnopqrstuvwxyz123456 vazou")
    s = obs.summary()
    assert [x["status"] for x in s["stages"]] == ["PASS", "BLOCKED", "FAIL"]
    assert s["status"] == "FAIL" and "sk-abc" not in json.dumps(s)
    lines = (obs.dir / "events.jsonl").read_text().splitlines()
    assert all(json.loads(line)["run_id"] == obs.run_id for line in lines)


def test_srt_formato():
    srt = build_srt([("um dois tres", 1.5), ("quatro", 0.5)], max_words=2)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,000\num dois")
    assert "00:00:01,500 --> 00:00:02,000\nquatro" in srt
