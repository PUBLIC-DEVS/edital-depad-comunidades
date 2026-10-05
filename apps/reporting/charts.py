"""Numeric presentation data for accessible CSS bars and a native SVG timeline."""


def operational_charts(summary, failures):
    max_analyst = max((a["total_assigned"] for a in summary["by_analyst"]), default=1) or 1
    for analyst in summary["by_analyst"]:
        analyst["series"] = [
            {
                "label": label,
                "count": analyst[key],
                "width": round(analyst[key] * 100 / max_analyst, 2),
                "tone": tone,
            }
            for label, key, tone in [
                ("Atribuídos", "total_assigned", "neutral"),
                ("Em andamento", "under_analysis", "info"),
                ("Concluídos", "concluded", "success"),
            ]
        ]
    groups = [
        {"label": "Sem grupo" if code == "SEM_GRUPO" else code, "count": count}
        for code, count in summary["by_group"].items()
    ]
    max_group = max((g["count"] for g in groups), default=1) or 1
    for group in groups:
        group["width"] = round(group["count"] * 100 / max_group, 2)
    max_failures = max((f["failure_count"] for f in failures), default=1) or 1
    for failure in failures:
        failure["width"] = round(failure["failure_count"] * 100 / max_failures, 2)
    points = []
    timeline = summary["timeline"]
    if summary["show_timeline"]:
        span = (timeline[-1]["date"] - timeline[0]["date"]).days or 1
        max_count = max(p["count"] for p in timeline) or 1
        for p in timeline:
            points.append(
                {
                    **p,
                    "x": round(40 + (p["date"] - timeline[0]["date"]).days * 620 / span, 2),
                    "y": round(180 - p["count"] * 140 / max_count, 2),
                }
            )
    return {
        "chart_groups": groups,
        "top_failures": failures,
        "timeline_points": points,
        "timeline_max": max((p["count"] for p in points), default=0),
        "timeline_path": " ".join(f"{p['x']},{p['y']}" for p in points),
    }
