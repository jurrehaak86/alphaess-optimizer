"""Generate dashboard/battery-view.yaml.

The plan chart exists twice (today, and today + tomorrow once prices are published).
Both come from one definition here so they never drift apart. Needs PyYAML.

    python3 dashboard/build_view.py
"""
import pathlib

import yaml

OUT = pathlib.Path(__file__).with_name("battery-view.yaml")

# Default entity IDs for an inverter device called "AlphaESS Inverter".
OPT = "optimizer_alphaess_inverter"
INV = "alphaess_inverter"
PRICE = "sensor.nordpool_kwh_nl_eur_3_10_0"
ACTION = f"sensor.{OPT}_action"

BANDS = [  # action, legend name, colour, opacity
    ("charge", "Charge", "#2e7d32", 0.3),
    ("discharge", "Discharge", "#c62828", 0.3),
    ("hold", "Hold", "#f9a825", 0.3),
    ("balance", "Balance", "#4fc3f7", 0.18),
]

PRICE_COLOURS = [
    (0, "Pink"), (0.1, "Blue"), (0.15, "Light Blue"), (0.2, "Cyan"), (0.25, "Green"),
    (0.3, "Lime"), (0.35, "Yellow"), (0.4, "Orange"), (0.45, "Red"), (0.5, "Purple"),
]


def band_future(action, name, colour, opacity):
    """Planned quarters from now on, from the plan_quarters attribute."""
    return {
        "entity": ACTION, "name": name, "yaxis_id": "action", "type": "area",
        "curve": "stepline", "stroke_width": 0, "color": colour, "opacity": opacity,
        "show": {"legend_value": False},
        "data_generator": (
            "const q = entity.attributes.plan_quarters || [];\n"
            "const now = Date.now();\n"
            f"const out = q.map(p => [Math.max(new Date(p[0]).getTime(), now), p[1] === '{action}' ? 1 : 0]);\n"
            "if (q.length) out.push([new Date(q[q.length - 1][0]).getTime() + 900000, 0]);\n"
            "return out;\n"),
    }


def band_past(action, name, colour, opacity):
    """Earlier today: the history of the Action sensor."""
    return {
        "entity": ACTION, "name": f"{name} (past)", "yaxis_id": "action", "type": "area",
        "curve": "stepline", "stroke_width": 0, "color": colour, "opacity": opacity,
        "extend_to": "now", "show": {"legend_value": False, "in_legend": False},
        "transform": f"return x === '{action}' ? 1 : 0;",
    }


def chart(two_days: bool):
    prices = ("[...(a.raw_today || []), ...(a.tomorrow_valid ? (a.raw_tomorrow || []) : [])]"
              if two_days else "(a.raw_today || [])")
    series = []
    for b in BANDS:
        series += [band_future(*b), band_past(*b)]
    series += [
        {"entity": PRICE, "name": "Price", "yaxis_id": "price", "type": "line",
         "curve": "stepline", "stroke_width": 2,
         "color_threshold": [{"value": v, "color": c} for v, c in PRICE_COLOURS],
         "data_generator": (
             "const a = entity.attributes;\n"
             f"const r = {prices};\n"
             "return r.map(p => [new Date(p.start).getTime(), Number(p.value)]);\n")},
        {"entity": ACTION, "name": "SoC plan", "yaxis_id": "soc", "type": "line",
         "curve": "straight", "stroke_width": 2, "stroke_dash": 4, "color": "#1e88e5",
         "show": {"legend_value": False},
         "data_generator": (
             "return (entity.attributes.plan_quarters || []).map(p =>\n"
             "  [new Date(p[0]).getTime() + 15 * 60 * 1000, p[2]]);\n")},
        {"entity": f"sensor.{INV}_battery_state_of_charge", "name": "SoC", "yaxis_id": "soc",
         "type": "line", "stroke_width": 2, "color": "#1e88e5", "extend_to": "now",
         "group_by": {"func": "last", "duration": "15min"}},
        # Invisible series that pins the price axis just around the lowest and highest price.
        {"entity": PRICE, "name": "Range", "yaxis_id": "price", "type": "line",
         "stroke_width": 0, "opacity": 0, "color": "transparent",
         "show": {"in_header": False, "legend_value": False, "in_legend": False},
         "data_generator": (
             "const a = entity.attributes;\n"
             f"const r = {prices}.map(p => Number(p.value)).filter(v => !isNaN(v));\n"
             "if (!r.length) return [];\n"
             "const t0 = new Date(); t0.setHours(0, 0, 0, 0);\n"
             "const lo = Math.floor((Math.min(...r) - 0.02) * 100) / 100;\n"
             "const hi = Math.ceil((Math.max(...r) + 0.02) * 100) / 100;\n"
             "return [[t0.getTime(), hi], [t0.getTime() + 1000, lo]];\n")},
    ]
    return {
        "type": "conditional",
        "conditions": [{"condition": "state", "entity": PRICE, "attribute": "tomorrow_valid",
                        "state": "true" if two_days else "false"}],
        "card": {
            "type": "custom:apexcharts-card",
            "header": {"show": True, "show_states": False,
                       "title": "Battery plan today and tomorrow" if two_days else "Battery plan today"},
            "graph_span": "2d" if two_days else "1d",
            "span": {"start": "day"},
            "now": {"show": True, "label": "Now"},
            "experimental": {"color_threshold": True},
            "apex_config": {"legend": {"show": True}, "chart": {"height": 400, "width": "100%"}},
            "yaxis": [
                {"id": "price", "decimals": 2, "apex_config": {"title": {"text": "€/kWh"}}},
                {"id": "soc", "opposite": True, "min": 0, "max": 100, "decimals": 0,
                 "apex_config": {"title": {"text": "SoC %"}}},
                {"id": "action", "show": False, "min": 0, "max": 1},
            ],
            "series": series,
        },
        "grid_options": {"columns": "full"},
    }


def entity(eid, name=None, icon=None, cols=6):
    c = {"type": "entity", "entity": eid, "state_color": False,
         "grid_options": {"columns": cols, "rows": 2}}
    if name:
        c["name"] = name
    if icon:
        c["icon"] = icon
    return c


def tile(eid, name, icon, cols, rows=2, slider=False, vertical=False):
    c = {"type": "tile", "entity": eid, "name": name, "icon": icon,
         "grid_options": {"columns": cols, "rows": rows}}
    if vertical:
        c["vertical"] = True
    if slider:
        c["features"] = [{"type": "numeric-input", "style": "slider"}]
    return c


VIEW = {
    "title": "Battery",
    "path": "battery",
    "icon": "mdi:home-battery",
    "type": "sections",
    "max_columns": 3,
    "badges": [
        {"type": "entity", "entity": f"sensor.{INV}_battery_state_of_charge"},
        {"type": "entity", "entity": f"sensor.{INV}_inverter_power"},
        {"type": "entity", "entity": ACTION},
    ],
    "sections": [
        {"type": "grid", "column_span": 3, "cards": [
            {"type": "heading", "heading": "Battery plan", "heading_style": "title"},
            chart(True),
            chart(False),
        ]},
        {"type": "grid", "cards": [
            {"type": "heading", "heading": "Live", "heading_style": "title"},
            entity(f"sensor.{INV}_inverter_power", "Inverter power", "mdi:flash"),
            entity(f"sensor.{INV}_battery_state_of_charge", "Battery SoC"),
            entity(f"sensor.{INV}_current_pv_production", "PV production", "mdi:solar-power-variant"),
            entity(ACTION, "Optimizer", "mdi:battery-sync"),
            entity(f"sensor.{INV}_grid_power", "Grid power", "mdi:transmission-tower-import"),
            entity(f"sensor.{INV}_current_house_load", "House load", "mdi:home-lightning-bolt"),
            tile(f"select.{INV}_dispatch_mode", "Dispatch mode", "mdi:battery-sync-outline", 12, rows=1),
            entity(f"sensor.{OPT}_reserve", "Reserve", "mdi:battery-lock"),
            entity(f"sensor.{OPT}_charge_ceiling", "Max % from grid", "mdi:transmission-tower-import"),
        ]},
        {"type": "grid", "cards": [
            {"type": "heading", "heading": "Optimizer", "heading_style": "title"},
            {**tile(ACTION, "Optimizer now", "mdi:battery-sync", 12, rows=1),
             "state_content": ["reason"]},
            tile(f"sensor.{OPT}_next_charge", "Next charge", "mdi:battery-arrow-up", 12, rows=1),
            tile(f"sensor.{OPT}_next_discharge", "Next discharge", "mdi:battery-arrow-down", 12, rows=1),
            tile(f"sensor.{OPT}_next_hold", "Next hold", "mdi:battery-lock", 12, rows=1),
            tile(f"number.{OPT}_aggressiveness", "Aggressiveness (1 = own use, 10 = profit)",
                 "mdi:tune-variant", 12, slider=True),
            tile(f"number.{OPT}_backup_target", "Backup target", "mdi:battery-heart-variant", 6, slider=True),
            tile(f"number.{OPT}_backup_weight", "Backup weight", "mdi:weight", 6, slider=True),
            {"type": "history-graph", "hours_to_show": 24,
             "entities": [{"entity": ACTION, "name": "Optimizer"},
                          {"entity": f"select.{INV}_dispatch_mode", "name": "Dispatch mode"}]},
        ]},
    ],
}

HEADER = """\
# AlphaESS Battery Optimizer: example dashboard view (sections).
# Generated by dashboard/build_view.py, edit that file instead.
#
# Needs apexcharts-card from HACS (Frontend) for the plan chart.
# Entity IDs assume an inverter device called "AlphaESS Inverter" and a Nord Pool
# sensor called sensor.nordpool_kwh_nl_eur_3_10_0. Replace them if yours differ;
# see docs/dashboard.md.
"""


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.add_representer(
    str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s,
                                         style="|" if "\n" in s else None))

if __name__ == "__main__":
    OUT.write_text(HEADER + yaml.dump(VIEW, Dumper=_Dumper, sort_keys=False,
                                      allow_unicode=True, width=120))
    print(f"wrote {OUT}")
