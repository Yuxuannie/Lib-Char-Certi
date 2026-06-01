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


def test_patterns_low_coverage_and_no_data():
    log = ("DATA_HEALTH=LOW_COVERAGE: lib covers only 2780/66470 (4.2%) delay arcs\n"
           "DATA_HEALTH=NO_DATA: lib covers 0/120 hold arcs\n")
    f = {x.code: x for x in audit_stage({"stage": "build_pr_table", "status": "passed",
                                         "failures": [], "log_file": "/l"}, log)}
    assert f["low_coverage"].severity == "warn" and "2780/66470" in f["low_coverage"].message
    assert f["no_data"].severity == "error" and "0/120" in f["no_data"].message


def test_patterns_liberate_exit_and_sigma_empty():
    log = "EXIT: 1\nSigma-table diagnostic: x | matched arcs sampled=40 | with EMPTY sigma-table lookup=12\n"
    codes = {x.code for x in audit_stage({"stage": "lib_join_sigma", "status": "passed",
                                          "failures": [], "log_file": "/l"}, log)}
    assert "liberate_exit" in codes and "sigma_table_empty" in codes


def test_patterns_exit_zero_is_not_a_finding():
    codes = {x.code for x in audit_stage({"stage": "lib_join_sigma", "status": "passed",
                                          "failures": [], "log_file": "/l"}, "EXIT: 0\n")}
    assert "liberate_exit" not in codes
