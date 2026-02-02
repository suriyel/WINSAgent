# Product Requirement Specification (Spec)

## 1. 业务目标 (Objective)

### 解决什么问题？
电信网络优化场景中，用户需要对仿真前后的网络性能指标进行直观对比，以评估优化方案的效果。当前系统仅提供表格形式的数据展示，缺乏可视化对比能力，用户难以快速识别关键变化和优化成效。

### 成功指标是什么？
- 用户能够通过可视化图表快速识别仿真前后指标变化趋势
- 支持通过筛选和聚合操作聚焦关键区域和指标
- 图表类型自动适配，降低用户使用门槛

---

## 2. 功能清单 (Features)

| 模块 | 功能描述 | 验收标准 (AC) | 优先级 |
| :--- | :------- | :------------ | :----- |
| **数据对比工具** | 新增 `compare_simulation_data` 工具，对比仿真前后的小区级数据 | 1. 工具接收场景 ID 和对比指标参数<br>2. 自动查询根因数据和仿真数据<br>3. 计算差值并生成对比数据结构<br>4. 支持 1000 以内小区数据处理 | P0 |
| **SSE 事件** | 新增 `chart.data` 事件类型，传输对比数据到前端 | 1. 事件包含图表类型、数据、统计信息<br>2. 支持分组聚合和过滤参数 | P0 |
| **图表推荐** | 使用 @antv/ava 智能推荐最佳图表类型 | 1. Advisor.advise() 根据数据返回推荐图表<br>2. 自动模式直接使用最佳推荐 | P0 |
| **图表渲染** | 使用 @antv/g2 渲染对比图表 | 1. 支持多指标同时对比<br>2. 支持鼠标悬停显示详细数值 | P0 |
| **小区筛选** | 支持按区域和关键词筛选小区 | 1. 区域下拉选择器<br>2. 关键词搜索框<br>3. 筛选结果实时更新图表 | P1 |
| **指标筛选** | 支持多选显示的指标维度 | 1. 指标复选框<br>2. 至少保留一个指标 | P1 |
| **阈值过滤** | 支持按差值阈值过滤小区 | 1. 滑块控制最小差值<br>2. 默认值为 1.0<br>3. 过滤结果实时更新 | P1 |
| **分组聚合** | 按区域统计聚合数据 | 1. 计算各区域指标平均值<br>2. 显示汇总统计信息 | P1 |
| **图表切换** | 支持 Ava 推荐的多种图表类型切换 | 1. 显示 Ava 推荐的候选图表<br>2. 切换时保持筛选条件<br>3. 用户可手动选择 | P2 |
| **集成展示** | 图表嵌入对话消息流 | 1. 类似 HITL 卡片的展示方式<br>2. 支持折叠/展开 | P0 |

---

## 3. 技术约束与集成 (Technical Constraints)

### 数据流向
```
用户输入 → LangChain Agent → compare_simulation_data 工具
                                            ↓
    (查询根因数据 + 查询仿真数据 + 合并计算)
                                            ↓
                                    SSE: chart.data 事件
                                            ↓
                  Frontend: chatStore.handleSSEEvent()
                                            ↓
                           MessageBubble.render(ComparisonChart)
                                            ↓
              ComparisonChart: Ava 推荐 → G2 渲染
```

### 第三方接口
| 库 | 版本 | 用途 |
|---|------|------|
| @antv/ava | latest | 智能图表推荐 |
| @antv/g2 | latest | 图表渲染 |

### 异常处理逻辑
1. **数据获取失败**：返回错误事件，前端显示错误提示
2. **指标不匹配**：前后端指标数量不一致时，取交集并提示用户
3. **空数据**：显示"无数据"提示，不渲染图表
4. **Ava 推荐失败**：降级使用默认图表类型（分柱图）

---

## 4. 非功能性需求

### 性能要求
- 支持最多 1000 个小区数据的实时渲染
- 筛选和过滤操作响应时间 < 300ms
- 图表初始化时间 < 1s

### 安全性/权限控制
- 无特殊权限要求，遵循现有会话认证机制
- SSE 连接复用现有控制器，支持中断

---

## 5. 数据结构定义

### 后端 SSE 事件数据
```json
{
  "execution_id": "uuid",
  "chart_type": "grouped_bar",
  "data": {
    "cells": [
      {
        "cell_id": "460-00-100001",
        "area": "朝阳",
        "before": {"RSRP均值(dBm)": -85.2, "SINR均值(dB)": 12.5, "覆盖率(%)": 88.0},
        "after":  {"RSRP均值(dBm)": -82.1, "SINR均值(dB)": 15.2, "覆盖率(%)": 92.5},
        "diff":   {"RSRP均值(dBm)": 3.1,  "SINR均值(dB)": 2.7,  "覆盖率(%)": 4.5}
      }
    ],
    "indicators": ["RSRP均值(dBm)", "SINR均值(dB)", "覆盖率(%)"],
    "statistics": {
      "by_area": {
        "朝阳": {"before_avg": {...}, "after_avg": {...}, "diff_avg": {...}}
      },
      "summary": {"avg_improvement": {...}}
    },
    "filters": {
      "areas": ["朝阳", "海淀", "浦东", "西湖", "天河"],
      "threshold": 1.0
    }
  }
}
```

### 前端类型定义
```typescript
export interface CellComparisonData {
  cell_id: string;
  area: string;
  before: Record<string, number>;
  after: Record<string, number>;
  diff: Record<string, number>;
}

export interface ChartData {
  cells: CellComparisonData[];
  indicators: string[];
  statistics: {
    by_area: Record<string, Record<string, number>>;
    summary: Record<string, number>;
  };
  filters: {
    areas: string[];
    threshold: number;
  };
}

export interface ChartPending {
  execution_id: string;
  chart_type: string;
  data: ChartData;
}
```

---

## 6. 未决/待定事项 (TBD)

| 事项 | 说明 | 计划处理时间 |
|------|------|-------------|
| 图表导出功能 | 待用户确认是否需要 PNG/CSV 导出 | v0.2 |
| 多级分组聚合 | 当前仅支持按区域分组，如需多级分组需扩展 | v0.2 |
| 差值阈值默认值 | 当前设定为 1.0，可根据实际数据调整 | 迭代优化 |

---

## 7. 文件变更清单

### 后端
| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/app/agent/tools/telecom_tools.py` | 新增 | `compare_simulation_data` 工具 |
| `backend/app/sse/event_mapper.py` | 新增 | `chart.data` 事件类型 |

### 前端
| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `frontend/package.json` | 修改 | 新增 `@antv/ava`、`@antv/g2` 依赖 |
| `frontend/src/types/index.ts` | 新增 | `ChartPending`、`ChartData`、`CellComparisonData` 类型 |
| `frontend/src/services/sse.ts` | 新增 | `chart.data` 到 SSE_EVENT_TYPES |
| `frontend/src/stores/chatStore.ts` | 新增 | `chart.data` 事件处理器 |
| `frontend/src/components/chart/ComparisonChart.tsx` | 新建 | 图表主组件 |
| `frontend/src/components/chat/MessageBubble.tsx` | 修改 | 添加图表渲染逻辑 |
