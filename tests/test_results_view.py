"""Tests for the per-type results view + certification verdict + export (B)."""

from cert_data_process.runtime import summary as S

_REC = {
    "sigma": [
        {"corner": "c1", "type": "delay", "eBase": 100.0, "eW1": 100.0, "lBase": 93.2, "lW1": 96.0, "health": "OK"},
        {"corner": "c1", "type": "hold", "lBase": 91.5, "lW1": 91.5, "health": "OK"},
        {"corner": "c1", "type": "mpw", "lBase": 97.3, "lW1": 97.3, "health": "OK"},
    ],
    "moments": [
        {"corner": "c1", "type": "delay", "ms": 99.1, "std": 97.4, "skew": 100.0,
         "msW1": 99.5, "stdW1": 98.0, "skewW1": 100.0, "health": "OK"},
    ],
}


def test_sections_grouped_by_type_with_right_metrics():
    secs = S.per_type_sections(_REC, "base")
    assert [s["type"] for s in secs] == ["delay", "hold", "mpw"]
    delay = secs[0]
    assert delay["metrics"] == ["Early_Sigma", "Late_Sigma", "Meanshift", "Std", "Skew"]
    assert delay["rows"][0]["values"]["Late_Sigma"] == 93.2
    assert delay["rows"][0]["values"]["Meanshift"] == 99.1
    hold = next(s for s in secs if s["type"] == "hold")
    assert hold["metrics"] == ["Late_Sigma"]


def test_verdict_base_vs_waiver1():
    base = S.certification_verdict(_REC, "base")
    assert base["passed"] is False
    # base fails delay Late (93.2) and hold (91.5)
    assert ("delay", "c1", "Late_Sigma", 93.2) in base["failing"]
    assert ("hold", "c1", "Late_Sigma", 91.5) in base["failing"]
    w1 = S.certification_verdict(_REC, "w1")
    # with waiver1 delay Late rises to 96.0 (pass); only hold remains failing
    assert [f[:3] for f in w1["failing"]] == [("hold", "c1", "Late_Sigma")]


def test_verdict_all_pass():
    rec = {"sigma": [{"corner": "c1", "type": "hold", "lBase": 99.0, "lW1": 99.0, "health": "OK"}], "moments": []}
    assert S.certification_verdict(rec, "base")["passed"] is True


def test_flat_export_rows():
    rows = S.flat_export_rows(_REC, "base")
    assert rows[0] == ["Type", "Corner", "Metric", "Pass_Rate", "Coverage_Health"]
    assert len(rows) - 1 == 7  # delay 5 + hold 1 + mpw 1
    assert ["hold", "c1", "Late_Sigma", "91.5", "OK"] in rows
