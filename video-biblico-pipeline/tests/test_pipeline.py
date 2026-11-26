"""Testes de integração/E2E: rodam o pipeline real com LLM fake, ffmpeg real e workspace temporário."""
import json
import subprocess

import pytest

from vbp import approval
from vbp.config import load_config

from conftest import SpyProvider


def _streams(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.split()
    return sorted(out)


def _statuses(summary):
    return {s["stage"]: s["status"] for s in summary["stages"]}


def test_e2e_gate_aprovacao_render_e_idempotencia(make_pipeline, episode):  # E2E-01
    p1 = make_pipeline()
    p1.state.add_episode(*episode)
    s1 = p1.run("EP001")
    assert _statuses(s1) == {"ROTEIRO": "PASS", "STORYBOARD": "PASS", "APROVACAO": "BLOCKED"}
    assert (p1.ep_dir("EP001") / "REVISAO.txt").exists()
    assert (p1.ep_dir("EP001") / "roteiro.json.explain.json").exists()

    approval.approve(p1.state, "EP001", p1.ep_dir("EP001"), "Revisor Teste")
    spy = SpyProvider()
    p2 = make_pipeline(providers=[spy])
    s2 = p2.run("EP001")
    st = _statuses(s2)
    assert st["ROTEIRO"] == "SKIPPED" and st["STORYBOARD"] == "SKIPPED"  # idempotência: nada refeito
    assert st["RENDER"] == "PASS" and st["PUBLICACAO"] == "PASS" and s2["status"] == "PASS"
    assert spy.prompts == [] and s2["metrics"]["llm_calls"] == 0  # nenhum custo na segunda execução
    d = p2.ep_dir("EP001")
    assert _streams(d / "video.mp4") == ["audio", "subtitle", "video"]
    assert (d / "thumbnail.png").exists() and (d / "legendas.srt").read_text().startswith("1\n")
    plan = json.loads((d / "publish_plan.json").read_text())
    assert plan["modo"] == "DRY_RUN" and plan["metadata"]["status"]["privacyStatus"] == "private"
    assert (p2.obs.dir / "run_summary.json").exists()


def test_alterar_conteudo_invalida_aprovacao(make_pipeline, episode):  # TI-01
    p = make_pipeline()
    p.state.add_episode(*episode)
    p.run("EP001")
    d = p.ep_dir("EP001")
    approval.approve(p.state, "EP001", d, "Revisor")
    roteiro = json.loads((d / "roteiro.json").read_text())
    roteiro["conclusao"] += " Frase adicionada depois da aprovação."
    (d / "roteiro.json").write_text(json.dumps(roteiro, ensure_ascii=False))
    ok, why = approval.is_approved(p.state, "EP001", d)
    assert not ok and "hash" in why
    p2 = make_pipeline()
    s = p2.run("EP001")
    assert _statuses(s).get("APROVACAO") == "BLOCKED" and "PUBLICACAO" not in _statuses(s)


def test_ajuste_humano_volta_como_feedback(make_pipeline, episode):  # TI-02
    p = make_pipeline()
    p.state.add_episode(*episode)
    p.run("EP001")
    approval.request_changes(p.state, "EP001", p.ep_dir("EP001"), "Revisor", "Explique melhor o contexto do vale de Elá")
    spy = SpyProvider()
    p2 = make_pipeline(providers=[spy])
    s = p2.run("EP001", until="ROTEIRO")
    assert _statuses(s)["ROTEIRO"] == "PASS"
    assert "Explique melhor o contexto do vale de Elá" in spy.prompts[0]


def test_validacao_falha_bloqueia_com_diagnostico(make_pipeline, episode):  # TI-03
    ruim = SpyProvider(lambda p: json.dumps({"titulo": "x", "secoes": []}))
    p = make_pipeline(providers=[ruim])
    p.state.add_episode(*episode)
    s = p.run("EP001")
    assert _statuses(s)["ROTEIRO"] == "BLOCKED"
    assert len(ruim.prompts) == 2  # limitado a max_tentativas_por_etapa
    assert "CORRIJA OS PROBLEMAS" in ruim.prompts[1]  # 2ª tentativa recebe o feedback da 1ª
    d = p.ep_dir("EP001")
    assert (d / "roteiro.rejeitado.json").exists() and (d / "diagnostico_roteiro.json").exists()


def test_orcamento_estourado_bloqueia(tmp_path, make_pipeline, episode):  # TI-04
    cfg = load_config(path=tmp_path / "x.toml", overrides={"geral": {"workspace": str(tmp_path / "ws2")},
                                                         "orcamento": {"max_chamadas_llm": 0}})
    p = make_pipeline(config=cfg)
    p.state.add_episode(*episode)
    s = p.run("EP001")
    stage = s["stages"][0]
    assert stage["status"] == "BLOCKED" and "orçamento" in stage["reason"]
    assert (p.ep_dir("EP001") / "diagnostico_roteiro.json").exists()


def test_provedor_externo_bloqueia_com_instrucao(tmp_path, make_pipeline, episode, cfg):  # TI-05
    cfg["imagens"]["provedor"] = "externo"
    p = make_pipeline(config=cfg)
    p.state.add_episode(*episode)
    p.run("EP001")
    approval.approve(p.state, "EP001", p.ep_dir("EP001"), "Revisor")
    s = make_pipeline(config=cfg).run("EP001")
    img = next(x for x in s["stages"] if x["stage"] == "IMAGENS")
    assert img["status"] == "BLOCKED" and "prompts.json" in img["reason"]
    assert (p.ep_dir("EP001") / "imagens" / "prompts.json").exists()


@pytest.mark.parametrize("live", [True])
def test_publicacao_live_nunca_sem_aprovacao(make_pipeline, episode, live):  # SEC-01
    p = make_pipeline(live=live)
    p.state.add_episode(*episode)
    s = p.run("EP001")
    assert "PUBLICACAO" not in _statuses(s)
    with pytest.raises(Exception):
        p.stage_publish(p.state.episode("EP001"), {}, None)
