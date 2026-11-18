"""Running tools use the same imported measurements as the dashboard."""

from reptrace.training.running import METRICS, compare_runs, running_totals
from reptrace.reports.running import render_running_report

NAMES = {
    "get_running_history",
    "get_running_detail",
    "compare_running_runs",
    "export_running_report",
}


def call(tools, name, args):
    from reptrace.coaching.assistant import check_dates

    if name == "get_running_history":
        start, end = args.get("from_date"), args.get("to_date")
        check_dates(start, end)
        limit = args.get("limit", 20)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("Choose a limit from 1 to 100")
        runs = sorted(
            [
                r
                for r in tools.data.get("runs", [])
                if (not start or r["date"] >= start) and (not end or r["date"] <= end)
            ],
            key=lambda r: r["time"],
            reverse=True,
        )
        return {
            "summary": running_totals(runs),
            "runs": runs[:limit],
            "total": len(runs),
            "truncated": len(runs) > limit,
            "metricCatalog": METRICS,
            "note": "Summary covers all filtered runs. Import detail for dynamics, laps, zones and charts. Missing values are not zero.",
        }
    if not tools.running:
        raise ValueError("Running detail service is unavailable")

    def detail(identity):
        runs = tools.data.get("runs", [])
        if identity != "latest" and not any(r["id"] == str(identity) for r in runs):
            raise ValueError("Choose an ID from get_running_history")
        result = tools.running({"id": identity})
        # Keep subsequent tool results in this turn coherent with imported detail.
        tools.data["runs"] = [
            {**r, **result["summary"]} if r["id"] == result["summary"]["id"] else r
            for r in runs
        ]
        return result

    if name == "compare_running_runs":
        left, right = detail(args["left_id"]), detail(args["right_id"])
        return {
            "left": left["summary"],
            "right": right["summary"],
            "metrics": compare_runs(left["summary"], right["summary"]),
            "warnings": [d["warning"] for d in (left, right) if d.get("warning")],
            "note": "Change is right minus left. Lower pace is faster; different distance, terrain and conditions affect comparisons.",
        }
    result = detail(args["run_id"])
    if name == "export_running_report":
        document = render_running_report(result)
        tools.artifacts.append(
            {
                "kind": "html_report",
                "title": "Running report",
                "filename": "running-report.html",
                "html": document,
            }
        )
        return {
            "queued": True,
            "summary": result["summary"],
            "warning": result.get("warning"),
            "delivery": "The complete HTML report with charts, zones, dynamics and laps will be attached.",
        }
    # Bound the coach context. The full charts remain available in the report.
    return {key: value for key, value in result.items() if key != "samples"} | {
        "chartMetrics": sorted(
            {
                key
                for row in result.get("samples", [])
                for key, value in row.items()
                if value is not None
            }
        ),
        "chartSampleCount": len(result.get("samples", [])),
    }
