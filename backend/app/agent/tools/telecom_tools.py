"""Telecom network optimization tools — digital twin scenario analysis.

These tools support querying network coverage scenarios, root cause analysis,
and optimization simulation results at both cell-level and grid-level.
"""

from __future__ import annotations

import json
import random

from langchain.tools import tool

from app.agent.tools.registry import tool_registry


# ---------------------------------------------------------------------------
# Indicator mapping: root cause → simulation (for compare tool)
# ---------------------------------------------------------------------------

INDICATOR_MAPPING: dict[str, str] = {
    "RSRP均值(dBm)":     "仿真RSRP均值(dBm)",
    "SINR均值(dB)":      "仿真SINR均值(dB)",
    "MR覆盖率(%)":       "仿真覆盖率(%)",
    "RRC连接成功率(%)":   "仿真RRC连接成功率(%)",
}


# ---------------------------------------------------------------------------
# Available chart types for compare_simulation_data (LLM selects)
# ---------------------------------------------------------------------------

AVAILABLE_CHART_TYPES: list[dict[str, str]] = [
    {"grouped_bar_chart": "分组柱状图 - 适用于分组对比分析，展示多个小区优化前后指标数值的直观对比"},
    {"line_chart": "折线图 - 适用于展示指标随小区变化的趋势对比"},
    {"stacked_bar_chart": "堆叠柱状图 - 适用于展示优化前后指标叠加的总量对比"},
    {"scatter_plot": "散点图 - 适用于探索优化前后数值关系、检测异常小区"},
    {"heatmap": "热力图 - 适用于大规模数据集的差值分布可视化"},
    {"table": "数据表格 - 适用于需要查看精确数值的场景"},
]

VALID_CHART_TYPES: set[str] = {
    k for d in AVAILABLE_CHART_TYPES for k in d
}


# ---------------------------------------------------------------------------
# Mock scenario data
# ---------------------------------------------------------------------------

MOCK_SCENARIOS = [
    {
        "digitaltwinsId": "DT20260101",
        "description": "朝阳区CBD区域4G/5G弱覆盖场景分析",
        "area": "朝阳区",
        "network_type": "4G/5G",
        "issue_type": "弱覆盖",
    },
    {
        "digitaltwinsId": "DT20260102",
        "description": "海淀区中关村越区覆盖干扰场景分析",
        "area": "海淀区",
        "network_type": "5G",
        "issue_type": "越区覆盖",
    },
    {
        "digitaltwinsId": "DT20260103",
        "description": "浦东新区陆家嘴高干扰高负荷场景分析",
        "area": "浦东新区",
        "network_type": "4G",
        "issue_type": "高干扰",
    },
    {
        "digitaltwinsId": "DT20260104",
        "description": "西湖区景区弱覆盖及容量不足场景分析",
        "area": "西湖区",
        "network_type": "4G/5G",
        "issue_type": "弱覆盖",
    },
    {
        "digitaltwinsId": "DT20260105",
        "description": "天河区珠江新城高话务容量场景分析",
        "area": "天河区",
        "network_type": "5G",
        "issue_type": "高负荷",
    },
]

# ---------------------------------------------------------------------------
# Available indicators
# ---------------------------------------------------------------------------

CELL_ROOT_CAUSE_INDICATORS = [
    "RSRP均值(dBm)", "SINR均值(dB)", "下行PRB利用率(%)", "上行PRB利用率(%)",
    "MR覆盖率(%)", "RRC连接成功率(%)", "切换成功率(%)", "下行流量(GB)", "用户数",
]

GRID_ROOT_CAUSE_INDICATORS = [
    "RSRP(dBm)", "SINR(dB)", "RSRQ(dB)", "重叠覆盖度",
    "下行速率(Mbps)", "上行速率(Mbps)", "覆盖电平(dBm)",
]

CELL_SIMULATION_INDICATORS = [
    "仿真RSRP均值(dBm)", "仿真SINR均值(dB)", "仿真下行速率(Mbps)",
    "仿真上行速率(Mbps)", "仿真覆盖率(%)", "仿真RRC连接成功率(%)",
]

GRID_SIMULATION_INDICATORS = [
    "仿真RSRP(dBm)", "仿真SINR(dB)", "仿真RSRQ(dB)",
    "仿真重叠覆盖度", "仿真下行速率(Mbps)", "仿真上行速率(Mbps)",
]


# ---------------------------------------------------------------------------
# Mock data generators
# ---------------------------------------------------------------------------

def _generate_cell_root_cause_data(scenario_id: str, indicators: list[str]) -> list[dict]:
    """Generate mock cell-level root cause analysis data."""
    random.seed(hash(scenario_id) % 2**32)

    base_coords = {
        "DT20260101": (116.446, 39.922, "朝阳"),
        "DT20260102": (116.310, 39.985, "海淀"),
        "DT20260103": (121.505, 31.240, "浦东"),
        "DT20260104": (120.150, 30.250, "西湖"),
        "DT20260105": (113.325, 23.135, "天河"),
    }
    base_lon, base_lat, _ = base_coords.get(scenario_id, (116.4, 39.9, "默认"))

    rows = []
    for i in range(15):
        row: dict = {
            "小区id": f"460-00-{100001 + i}",
            "longitude": round(base_lon + random.uniform(-0.03, 0.03), 4),
            "latitude": round(base_lat + random.uniform(-0.03, 0.03), 4),
        }
        all_values = {
            "RSRP均值(dBm)": round(random.uniform(-110, -75), 1),
            "SINR均值(dB)": round(random.uniform(-2, 18), 1),
            "下行PRB利用率(%)": round(random.uniform(30, 95), 1),
            "上行PRB利用率(%)": round(random.uniform(20, 80), 1),
            "MR覆盖率(%)": round(random.uniform(40, 98), 1),
            "RRC连接成功率(%)": round(random.uniform(88, 99.5), 1),
            "切换成功率(%)": round(random.uniform(85, 99), 1),
            "下行流量(GB)": round(random.uniform(50, 300), 1),
            "用户数": random.randint(200, 3000),
        }
        for ind in indicators:
            if ind in all_values:
                row[ind] = all_values[ind]
        rows.append(row)
    return rows


def _generate_grid_root_cause_data(scenario_id: str, indicators: list[str]) -> list[dict]:
    """Generate mock grid-level root cause analysis data."""
    random.seed(hash(scenario_id + "_grid") % 2**32)

    base_coords = {
        "DT20260101": (116.446, 39.922),
        "DT20260102": (116.310, 39.985),
        "DT20260103": (121.505, 31.240),
        "DT20260104": (120.150, 30.250),
        "DT20260105": (113.325, 23.135),
    }
    base_lon, base_lat = base_coords.get(scenario_id, (116.4, 39.9))

    rows = []
    for i in range(15):
        row: dict = {
            "longitude": round(base_lon + random.uniform(-0.02, 0.02), 4),
            "latitude": round(base_lat + random.uniform(-0.02, 0.02), 4),
        }
        all_values = {
            "RSRP(dBm)": round(random.uniform(-115, -70), 1),
            "SINR(dB)": round(random.uniform(-3, 20), 1),
            "RSRQ(dB)": round(random.uniform(-18, -5), 1),
            "重叠覆盖度": random.randint(1, 8),
            "下行速率(Mbps)": round(random.uniform(5, 200), 1),
            "上行速率(Mbps)": round(random.uniform(2, 80), 1),
            "覆盖电平(dBm)": round(random.uniform(-110, -65), 1),
        }
        for ind in indicators:
            if ind in all_values:
                row[ind] = all_values[ind]
        rows.append(row)
    return rows


def _generate_cell_simulation_data(scenario_id: str, indicators: list[str]) -> list[dict]:
    """Generate mock cell-level simulation data (improved after optimization)."""
    random.seed(hash(scenario_id + "_sim") % 2**32)

    base_coords = {
        "DT20260101": (116.446, 39.922),
        "DT20260102": (116.310, 39.985),
        "DT20260103": (121.505, 31.240),
        "DT20260104": (120.150, 30.250),
        "DT20260105": (113.325, 23.135),
    }
    base_lon, base_lat = base_coords.get(scenario_id, (116.4, 39.9))

    rows = []
    for i in range(15):
        row: dict = {
            "小区id": f"460-00-{100001 + i}",
            "longitude": round(base_lon + random.uniform(-0.03, 0.03), 4),
            "latitude": round(base_lat + random.uniform(-0.03, 0.03), 4),
        }
        # Simulation values are generally better than root cause values
        all_values = {
            "仿真RSRP均值(dBm)": round(random.uniform(-95, -65), 1),
            "仿真SINR均值(dB)": round(random.uniform(5, 25), 1),
            "仿真下行速率(Mbps)": round(random.uniform(50, 500), 1),
            "仿真上行速率(Mbps)": round(random.uniform(20, 150), 1),
            "仿真覆盖率(%)": round(random.uniform(85, 99.5), 1),
            "仿真RRC连接成功率(%)": round(random.uniform(95, 99.9), 1),
        }
        for ind in indicators:
            if ind in all_values:
                row[ind] = all_values[ind]
        rows.append(row)
    return rows


def _generate_grid_simulation_data(scenario_id: str, indicators: list[str]) -> list[dict]:
    """Generate mock grid-level simulation data (improved after optimization)."""
    random.seed(hash(scenario_id + "_grid_sim") % 2**32)

    base_coords = {
        "DT20260101": (116.446, 39.922),
        "DT20260102": (116.310, 39.985),
        "DT20260103": (121.505, 31.240),
        "DT20260104": (120.150, 30.250),
        "DT20260105": (113.325, 23.135),
    }
    base_lon, base_lat = base_coords.get(scenario_id, (116.4, 39.9))

    rows = []
    for i in range(15):
        row: dict = {
            "longitude": round(base_lon + random.uniform(-0.02, 0.02), 4),
            "latitude": round(base_lat + random.uniform(-0.02, 0.02), 4),
        }
        # Simulation values are improved
        all_values = {
            "仿真RSRP(dBm)": round(random.uniform(-90, -60), 1),
            "仿真SINR(dB)": round(random.uniform(8, 28), 1),
            "仿真RSRQ(dB)": round(random.uniform(-12, -3), 1),
            "仿真重叠覆盖度": random.randint(1, 4),
            "仿真下行速率(Mbps)": round(random.uniform(80, 350), 1),
            "仿真上行速率(Mbps)": round(random.uniform(30, 120), 1),
        }
        for ind in indicators:
            if ind in all_values:
                row[ind] = all_values[ind]
        rows.append(row)
    return rows


def _format_table(rows: list[dict]) -> str:
    """Format rows as a [DATA_TABLE] block with CSV content."""
    if not rows:
        return "无数据"
    headers = list(rows[0].keys())
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(row.get(h, "")) for h in headers))
    return "[DATA_TABLE]\n" + "\n".join(lines) + "\n[/DATA_TABLE]"


# ---------------------------------------------------------------------------
# Tool 1: match_scenario (查询类，无HITL)
# ---------------------------------------------------------------------------

@tool
def match_scenario(description: str) -> str:
    """根据用户描述的区域和问题类型，匹配对应的数字孪生仿真场景。
    返回匹配的场景信息，包含 digitaltwinsId 用于后续根因分析和优化仿真查询。

    参数说明：
    - description: 用户描述的区域名称、问题类型等关键词（如"朝阳区弱覆盖"）
    """
    desc_lower = description.lower()
    matched = []
    for s in MOCK_SCENARIOS:
        # Match by area name or issue type or description keywords
        if (s["area"] in description
                or s["issue_type"] in description
                or s["network_type"] in description
                or any(kw in desc_lower for kw in s["description"].lower().split())):
            matched.append(s)

    if not matched:
        return f"未找到与{description}匹配的场景。请检查区域名称或问题描述。"

    result_lines = [f"找到 {len(matched)} 个匹配场景：\n"]
    for s in matched:
        result_lines.append(
            f"- 场景ID: {s['digitaltwinsId']}\n"
            f"  描述: {s['description']}\n"
            f"  区域: {s['area']}\n"
            f"  网络类型: {s['network_type']}\n"
            f"  问题类型: {s['issue_type']}"
        )
    return "\n".join(result_lines)


# ---------------------------------------------------------------------------
# Tool 2: query_root_cause_analysis (查询类，无HITL)
# ---------------------------------------------------------------------------

@tool
def query_root_cause_analysis(
    digitaltwins_id: str,
    level: str,
    indicators: list[str],
) -> str:
    """根据数字孪生场景ID查询根因分析任务结果。
    支持小区级(cell)和栅格级(grid)两种粒度的分析结果。
    根据用户关注的问题类型，选择相关指标进行查询，不需要查询全部指标。

    参数说明：
    - digitaltwins_id: 数字孪生场景唯一标识（如 DT20260101），通过 match_scenario 获取
    - level: 分析粒度，"cell"表示小区级，"grid"表示栅格级
    - indicators: 需要查询的指标名称列表。
      小区级可选指标: RSRP均值(dBm), SINR均值(dB), 下行PRB利用率(%), 上行PRB利用率(%), MR覆盖率(%), RRC连接成功率(%), 切换成功率(%), 下行流量(GB), 用户数
      栅格级可选指标: RSRP(dBm), SINR(dB), RSRQ(dB), 重叠覆盖度, 下行速率(Mbps), 上行速率(Mbps), 覆盖电平(dBm)
    """
    # Validate scenario exists
    scenario = next((s for s in MOCK_SCENARIOS if s["digitaltwinsId"] == digitaltwins_id), None)
    if not scenario:
        return f"未找到场景 {digitaltwins_id}，请先使用 match_scenario 工具获取有效的场景ID。"

    # Validate level
    if level not in ("cell", "grid"):
        return f"无效的分析粒度 '{level}'，请使用 'cell'（小区级）或 'grid'（栅格级）。"

    # Validate indicators
    valid_indicators = CELL_ROOT_CAUSE_INDICATORS if level == "cell" else GRID_ROOT_CAUSE_INDICATORS
    invalid = [ind for ind in indicators if ind not in valid_indicators]
    if invalid:
        return (
            f"以下指标不在{'小区级' if level == 'cell' else '栅格级'}可选范围内: {invalid}\n"
            f"可选指标: {valid_indicators}"
        )

    # Generate mock data
    if level == "cell":
        rows = _generate_cell_root_cause_data(digitaltwins_id, indicators)
    else:
        rows = _generate_grid_root_cause_data(digitaltwins_id, indicators)

    level_name = "小区级" if level == "cell" else "栅格级"
    header = (
        f"场景 {digitaltwins_id} - {scenario['description']}的{level_name}根因分析结果：\n"
        f"查询指标: {', '.join(indicators)}\n"
        f"数据总量: {len(rows)}条记录\n\n"
    )
    return header + _format_table(rows)


# ---------------------------------------------------------------------------
# Tool 3: query_simulation_results (查询类，无HITL)
# ---------------------------------------------------------------------------

@tool
def query_simulation_results(
    digitaltwins_id: str,
    level: str,
    indicators: list[str],
) -> str:
    """根据数字孪生场景ID查询优化仿真后的结果数据。
    仿真结果反映了优化方案实施后的预期网络性能。
    支持小区级(cell)和栅格级(grid)两种粒度的仿真结果。

    参数说明：
    - digitaltwins_id: 数字孪生场景唯一标识（如 DT20260101），通过 match_scenario 获取
    - level: 分析粒度，"cell"表示小区级，"grid"表示栅格级
    - indicators: 需要查询的仿真指标名称列表。
      小区级可选指标: 仿真RSRP均值(dBm), 仿真SINR均值(dB), 仿真下行速率(Mbps), 仿真上行速率(Mbps), 仿真覆盖率(%), 仿真RRC连接成功率(%)
      栅格级可选指标: 仿真RSRP(dBm), 仿真SINR(dB), 仿真RSRQ(dB), 仿真重叠覆盖度, 仿真下行速率(Mbps), 仿真上行速率(Mbps)
    """
    scenario = next((s for s in MOCK_SCENARIOS if s["digitaltwinsId"] == digitaltwins_id), None)
    if not scenario:
        return f"未找到场景 {digitaltwins_id}，请先使用 match_scenario 工具获取有效的场景ID。"

    if level not in ("cell", "grid"):
        return f"无效的分析粒度 '{level}'，请使用 'cell'（小区级）或 'grid'（栅格级）。"

    valid_indicators = CELL_SIMULATION_INDICATORS if level == "cell" else GRID_SIMULATION_INDICATORS
    invalid = [ind for ind in indicators if ind not in valid_indicators]
    if invalid:
        return (
            f"以下指标不在{'小区级' if level == 'cell' else '栅格级'}仿真可选范围内: {invalid}\n"
            f"可选指标: {valid_indicators}"
        )

    if level == "cell":
        rows = _generate_cell_simulation_data(digitaltwins_id, indicators)
    else:
        rows = _generate_grid_simulation_data(digitaltwins_id, indicators)

    level_name = "小区级" if level == "cell" else "栅格级"
    header = (
        f"场景 {digitaltwins_id} - {scenario['description']}的{level_name}优化仿真结果：\n"
        f"查询指标: {', '.join(indicators)}\n"
        f"数据总量: {len(rows)}条记录\n\n"
    )
    return header + _format_table(rows)


# ---------------------------------------------------------------------------
# Tool 4: compare_simulation_data (查询类，无HITL)
# ---------------------------------------------------------------------------

@tool
def compare_simulation_data(
    digitaltwins_id: str,
    indicators: list[str],
    chart_type: str = "grouped_bar_chart",
) -> str:
    """对比仿真前后的小区级网络性能指标数据。
    自动查询根因分析和仿真结果，计算差值并生成可视化对比数据。

    参数说明：
    - digitaltwins_id: 数字孪生场景唯一标识（如 DT20260101），通过 match_scenario 获取
    - indicators: 需要对比的根因指标列表，如 ["RSRP均值(dBm)", "SINR均值(dB)"]
      可选指标: RSRP均值(dBm), SINR均值(dB), MR覆盖率(%), RRC连接成功率(%)
    - chart_type: 图表类型，根据数据特征和用户需求选择最合适的类型
      可选值: grouped_bar_chart(分组柱状图,默认), line_chart(折线图), stacked_bar_chart(堆叠柱状图), scatter_plot(散点图), heatmap(热力图), table(数据表格)
    """
    # 1. 验证场景
    scenario = next(
        (s for s in MOCK_SCENARIOS if s["digitaltwinsId"] == digitaltwins_id),
        None,
    )
    if not scenario:
        return f"未找到场景 {digitaltwins_id}，请先使用 match_scenario 工具获取有效的场景ID。"

    # 2. 验证指标并映射
    valid = [ind for ind in indicators if ind in INDICATOR_MAPPING]
    if not valid:
        return (
            f"无有效对比指标。可选指标: {list(INDICATOR_MAPPING.keys())}"
        )
    sim_indicators = [INDICATOR_MAPPING[ind] for ind in valid]

    # 3. 获取根因数据和仿真数据
    root_rows = _generate_cell_root_cause_data(digitaltwins_id, valid)
    sim_rows = _generate_cell_simulation_data(digitaltwins_id, sim_indicators)

    # 4. 按 cell_id 合并，计算差值
    sim_map = {r["小区id"]: r for r in sim_rows}
    cells: list[dict] = []
    for root in root_rows:
        cid = root["小区id"]
        sim = sim_map.get(cid, {})
        before = {ind: root.get(ind, 0) for ind in valid}
        after = {ind: sim.get(INDICATOR_MAPPING[ind], 0) for ind in valid}
        diff = {ind: round(after[ind] - before[ind], 2) for ind in valid}
        cells.append({
            "cell_id": cid,
            "area": scenario["area"],
            "before": before,
            "after": after,
            "diff": diff,
        })

    if not cells:
        return "无法生成对比数据：未找到匹配的小区记录。"

    # 5. 统计聚合
    areas = sorted({c["area"] for c in cells})
    by_area: dict = {}
    for area in areas:
        area_cells = [c for c in cells if c["area"] == area]
        n = len(area_cells)
        by_area[area] = {
            "before_avg": {
                ind: round(sum(c["before"][ind] for c in area_cells) / n, 2)
                for ind in valid
            },
            "after_avg": {
                ind: round(sum(c["after"][ind] for c in area_cells) / n, 2)
                for ind in valid
            },
            "diff_avg": {
                ind: round(sum(c["diff"][ind] for c in area_cells) / n, 2)
                for ind in valid
            },
        }

    summary = {
        "avg_improvement": {
            ind: round(sum(c["diff"][ind] for c in cells) / len(cells), 2)
            for ind in valid
        }
    }

    # 6. 构建 chart_data JSON
    resolved_chart_type = chart_type if chart_type in VALID_CHART_TYPES else "grouped_bar_chart"
    chart_data = {
        "chart_type": resolved_chart_type,
        "data": {
            "cells": cells,
            "indicators": valid,
            "statistics": {"by_area": by_area, "summary": summary},
            "filters": {"areas": areas, "threshold": 1.0},
        },
    }

    # 7. 返回文本摘要 + [CHART_DATA] 块（由 ChartDataMiddleware 提取）
    text_summary = (
        f"场景 {digitaltwins_id} - {scenario['description']}的仿真前后对比完成：\n"
        f"对比指标: {', '.join(valid)}\n"
        f"小区数量: {len(cells)}\n"
        f"平均提升: {summary['avg_improvement']}\n"
    )

    chart_json = json.dumps(chart_data, ensure_ascii=False)
    return f"{text_summary}\n[CHART_DATA]{chart_json}[/CHART_DATA]"


# ---------------------------------------------------------------------------
# Register all telecom tools
# ---------------------------------------------------------------------------

def register_telecom_tools() -> None:
    """Register all telecom tools into the global registry."""
    tool_registry.register(match_scenario, category="query")
    tool_registry.register(query_root_cause_analysis, category="query")
    tool_registry.register(query_simulation_results, category="query")
    tool_registry.register(compare_simulation_data, category="query")
