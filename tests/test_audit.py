"""Pipeline audit: Finding extraction from stage dicts + log patterns."""

from cert_data_process.audit import Finding, audit_stage


def test_failed_stage_yields_error():
    se = {"stage": "lib_join_sigma", "status": "failed", "reason": "no_lib_inputs",
          "failures": [], "log_file": "/x.log"}
    f = audit_stage(se, "")
    assert any(x.severity == "error" and x.code == "stage_failed" for x in f)


def test_partial_and_failures_list():
    se = {"stage": "fmc_combine_data", "status": "partial",
          "processed": [1, 2], "failures": [
              {"reason": "no_scld_file", "detail": "corner X", "corner": "X"}],
          "log_file": "/x.log"}
    f = audit_stage(se, "")
    codes = {x.code for x in f}
    assert "partial" in codes
    assert "no_scld_file" in codes
    nl = next(x for x in f if x.code == "no_scld_file")
    assert nl.severity == "warn" and nl.pointer == "/x.log"
