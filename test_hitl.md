# HITL 测试指南

## 测试步骤

### 1. 启动后端
```bash
cd backend
python -m uvicorn app.main:app --reload
```

### 2. 启动前端
```bash
cd frontend
npm run dev
```

### 3. 触发 HITL 测试

在前端输入以下消息之一：

**选项 A - 直接触发 user_input 工具**:
```
请帮我完成一个需要我输入信息的任务
```

**选项 B - 明确要求**:
```
请询问我的邮箱地址，然后帮我发送一封邮件
```

### 4. 观察日志

#### 后端日志（终端）
应该看到：
```
[DEBUG] Interrupt detected! Value: ...
[DEBUG] Processing interrupt, getting state...
[DEBUG] Final state values: dict_keys(['messages', 'todo_list', 'pending_config', ...])
[DEBUG] pending_config: {'step_id': 'step_1', 'title': '需要您的输入', ...}
[DEBUG] Serialized data: {'pending_config': {...}, 'todo_list': [...]}
[DEBUG] Sending interrupt event: {...}
```

#### 前端日志（浏览器控制台）
应该看到：
```
[SSE] Interrupt event received: {type: 'interrupt', thread_id: '...', data: {...}}
[SSE] Setting pending_config: {step_id: 'step_1', title: '需要您的输入', ...}
[ConfigModal] Config changed: {step_id: 'step_1', ...}
[ConfigModal] Initializing values for config: ...
```

### 5. 预期行为

1. ✅ 后端检测到 `tool_name == "user_input"`
2. ✅ 设置 `pending_config` 到 state
3. ✅ 调用 `interrupt("waiting_for_user_input")`
4. ✅ Stream 循环检测到 `__interrupt__`
5. ✅ 调用 `graph.get_state()` 获取最新状态
6. ✅ 序列化 `pending_config`
7. ✅ 发送 SSE `interrupt` 事件
8. ✅ 前端接收事件
9. ✅ 调用 `setPendingConfig()`
10. ✅ ConfigModal 显示表单
11. ✅ 用户填写并提交
12. ✅ 调用 `/resume/{thread_id}`
13. ✅ 继续执行

## 常见问题排查

### ConfigModal 不显示
- [ ] 检查浏览器控制台是否有 `[SSE] Interrupt event received`
- [ ] 检查 `[ConfigModal] Config changed` 是否为非 null
- [ ] 检查 `pendingConfig` state 是否正确设置
- [ ] 检查 Workstation.tsx 是否正确传递 props

### interrupt 事件未接收
- [ ] 检查后端日志是否有 `[DEBUG] Interrupt detected`
- [ ] 检查后端是否正确发送 SSE 事件
- [ ] 检查网络面板（Network）SSE 连接是否正常
- [ ] 检查前端是否正确解析 SSE 数据

### 序列化错误
- [ ] 检查 `serialize_state_for_sse()` 是否正确处理所有字段
- [ ] 检查 `PendingConfigField` 是否包含不可序列化的对象
- [ ] 添加 try-catch 捕获序列化异常

## 调试工具

### 查看 SSE 流
在浏览器开发者工具：
1. Network 标签
2. 找到 `/chat/stream` 请求
3. 点击查看 EventStream 数据

### 手动测试 resume 端点
```bash
curl -X POST http://localhost:8000/api/v1/chat/resume/YOUR_THREAD_ID \
  -H "Content-Type: application/json" \
  -d '{"user_response": "test input"}'
```
