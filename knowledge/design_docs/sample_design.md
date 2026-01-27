# 存量系统API设计文档

## 1. 客户管理模块

### 1.1 搜索客户 API
- 接口：GET /api/v1/customers/search
- 参数：keyword (string) - 模糊搜索关键词
- 返回：客户列表，包含 customer_id, name, status, credit_level

### 1.2 验证客户 API
- 接口：GET /api/v1/customers/{customer_id}/validate
- 返回：验证结果，包含 valid (bool), name, status, credit_level
- 业务规则：状态为"冻结"或"注销"的客户验证不通过

## 2. 订单管理模块

### 2.1 创建订单 API
- 接口：POST /api/v1/orders
- 请求体：customer_id, items (product_code, quantity), delivery_address
- 前置条件：客户验证通过，库存充足
- 返回：order_id, status, estimated_delivery_date
- 业务规则：单笔订单金额超过10万需走审批流程

### 2.2 查询订单 API
- 接口：GET /api/v1/orders/{order_id}
- 返回：订单详情，包含状态流转记录

## 3. 库存管理模块

### 3.1 查询库存 API
- 接口：POST /api/v1/inventory/check
- 请求体：product_codes (list)
- 返回：各产品的 total_stock, available_stock, reserved_stock
