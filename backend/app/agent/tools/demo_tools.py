"""Demo tools simulating legacy system APIs.

These tools showcase the dependency-aware description pattern and serve as
integration test fixtures until real legacy API wrappers are developed.
"""

from __future__ import annotations

from langchain.tools import tool

from app.agent.middleware.missing_params import array_param, param_edit, string_param
from app.agent.tools.registry import tool_registry


# ---------------------------------------------------------------------------
# Tool 1: search_customer (查询类，无HITL)
# ---------------------------------------------------------------------------

@tool
def search_customer(keyword: str) -> str:
    """根据关键词搜索客户信息。返回匹配的客户编码和名称列表。

    参数说明：
    - keyword: 客户名称或编码的模糊搜索关键词
    """
    # Simulate legacy API response
    return (
        f"搜索结果 (关键词: {keyword}):\n"
        "1. C001 - 华东科技有限公司\n"
        "2. C002 - 南方电子集团\n"
        "3. C003 - 北方制造股份"
    )


# ---------------------------------------------------------------------------
# Tool 2: validate_customer (查询类，无HITL)
# ---------------------------------------------------------------------------

@tool
def validate_customer(customer_id: str) -> str:
    """验证客户编码的有效性并返回客户详细信息。

    依赖关系：可通过 search_customer 工具先查询获取客户编码。

    参数说明：
    - customer_id: 客户编码（如 C001）
    """
    # Simulate validation
    if customer_id.startswith("C"):
        return (
            f"客户 {customer_id} 验证通过。\n"
            f"名称: 华东科技有限公司\n"
            f"状态: 活跃\n"
            f"信用等级: A"
        )
    return f"客户 {customer_id} 验证失败：无效的客户编码。"


# ---------------------------------------------------------------------------
# Tool 3: create_order (变更类，需HITL确认)
# ---------------------------------------------------------------------------

@param_edit({
    "customer_id": string_param(
        title="客户编码",
        description="客户编码（如 C001），可通过 search_customer 查询",
        placeholder="例如: C001",
    ),
    "product_codes": array_param(
        item_type="string",
        title="产品编码列表",
        description="产品编码列表，需符合ERP编码规范",
        placeholder='例如: ["P001", "P002"]',
    ),
    "quantities": array_param(
        item_type="integer",
        title="数量列表",
        description="对应产品的数量列表，与产品编码一一对应",
        placeholder="例如: [10, 20]",
        min_items=1,
    ),
    "delivery_address": string_param(
        title="配送地址",
        description="配送地址，需包含省市区",
        placeholder="例如: 上海市浦东新区张江高科技园区",
    ),
})
@tool
def create_order(
    customer_id: str,
    product_codes: list[str],
    quantities: list[int],
    delivery_address: str,
) -> str:
    """创建订单。此为变更操作，执行前需用户确认。

    依赖关系：调用前需先通过 validate_customer 验证客户有效性。

    参数说明：
    - customer_id: 客户编码（可通过 search_customer 工具查询）
    - product_codes: 产品编码列表（需符合ERP编码规范，如 P001）
    - quantities: 对应产品的数量列表
    - delivery_address: 配送地址（需包含省市区）
    """
    items = ", ".join(
        f"{code}x{qty}" for code, qty in zip(product_codes, quantities)
    )
    return (
        f"订单创建成功！\n"
        f"客户: {customer_id}\n"
        f"明细: {items}\n"
        f"配送地址: {delivery_address}\n"
        f"订单号: ORD-20260128-001"
    )


# ---------------------------------------------------------------------------
# Tool 4: check_inventory (查询类，无HITL)
# ---------------------------------------------------------------------------

@tool
def check_inventory(product_codes: list[str]) -> str:
    """查询产品库存信息。

    参数说明：
    - product_codes: 产品编码列表
    """
    lines = []
    for code in product_codes:
        lines.append(f"{code}: 库存 150 件，可用 120 件")
    return "库存查询结果:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Register all demo tools
# ---------------------------------------------------------------------------

def register_demo_tools() -> None:
    """Register all demo tools into the global registry."""
    tool_registry.register(search_customer, category="query")
    tool_registry.register(validate_customer, category="query")
    tool_registry.register(create_order, category="mutation", requires_hitl=True)
    tool_registry.register(check_inventory, category="query")
