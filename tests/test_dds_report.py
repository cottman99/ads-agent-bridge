from pathlib import Path

import pytest

from ads_agent_bridge import dds_report


def _plan(tmp_path: Path) -> dict:
    return {
        "schema_version": "ads.dds-report/v1",
        "operation_id": "build_report",
        "workspace": str(tmp_path / "demo_wrk"),
        "dataset": str(tmp_path / "demo_wrk" / "data.ds"),
        "output_file": str(tmp_path / "demo_wrk" / "results.dds"),
        "page": "RF results",
        "equations": [{"name": "gain_db", "expression": "dB(S(2,1))"}],
        "plots": [
            {
                "name": "S parameters",
                "traces": ["dB(S(1,1))", "gain_db"],
                "rect": [1, 1, 10, 7],
            }
        ],
    }


def test_dds_plan_accepts_equations_and_plots(tmp_path: Path):
    plan = dds_report.validate_dds_plan(_plan(tmp_path))
    assert plan["plots"][0]["rect"] == [1, 1, 10, 7]


def test_dds_v2_accepts_multiple_pages_and_typed_plots(tmp_path: Path):
    plan = _plan(tmp_path)
    plan.pop("page")
    equations = plan.pop("equations")
    plots = plan.pop("plots")
    plan["schema_version"] = "ads.dds-report/v2"
    plan["pages"] = [
        {
            "name": "S parameter magnitude",
            "equations": equations,
            "plots": [{**plots[0], "kind": "rectangular"}],
        },
        {
            "name": "Complex response",
            "plots": [
                {
                    "kind": "polar",
                    "name": "S11 polar",
                    "traces": ["S(1,1)"],
                    "rect": [1, 1, 10, 10],
                }
            ],
        },
    ]

    normalized = dds_report.validate_dds_plan(plan)

    assert [page["name"] for page in normalized["pages"]] == [
        "S parameter magnitude",
        "Complex response",
    ]
    assert normalized["pages"][1]["plots"][0]["kind"] == "polar"


def test_dds_v2_rejects_duplicate_page_names(tmp_path: Path):
    plan = _plan(tmp_path)
    plot = {**plan.pop("plots")[0], "kind": "rectangular"}
    plan.pop("page")
    plan.pop("equations")
    plan["schema_version"] = "ads.dds-report/v2"
    plan["pages"] = [
        {"name": "Repeated", "plots": [plot]},
        {"name": "Repeated", "plots": [plot]},
    ]
    with pytest.raises(ValueError, match="invalid or duplicated"):
        dds_report.validate_dds_plan(plan)


def test_dds_v2_rejects_unknown_plot_kind(tmp_path: Path):
    plan = _plan(tmp_path)
    plot = {**plan.pop("plots")[0], "kind": "smith"}
    plan.pop("page")
    plan.pop("equations")
    plan["schema_version"] = "ads.dds-report/v2"
    plan["pages"] = [{"name": "RF", "plots": [plot]}]
    with pytest.raises(ValueError, match=r"pages\[0\]\.plots\[0\] is invalid"):
        dds_report.validate_dds_plan(plan)


def test_dds_plan_rejects_fractional_page_coordinates(tmp_path: Path):
    plan = _plan(tmp_path)
    plan["plots"][0]["rect"] = [1.5, 1, 10, 7]
    with pytest.raises(ValueError, match=r"plots\[0\] is invalid"):
        dds_report.validate_dds_plan(plan)


def test_dds_plan_rejects_raw_script(tmp_path: Path):
    plan = _plan(tmp_path)
    plan["python"] = "escape()"
    with pytest.raises(ValueError, match="unsupported fields"):
        dds_report.validate_dds_plan(plan)


def test_dds_output_must_be_inside_workspace(tmp_path: Path):
    plan = _plan(tmp_path)
    Path(plan["workspace"]).mkdir()
    Path(plan["dataset"]).touch()
    plan["output_file"] = str(tmp_path / "elsewhere.dds")
    with pytest.raises(ValueError, match="directly inside workspace"):
        dds_report.execute_dds_plan(plan)
