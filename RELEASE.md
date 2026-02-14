# WINS Agent Workstation - Release Notes

## Version 1.1.0 - 2026-02-14

### 新增功能 (New Features)

#### 语料检索系统 (Corpus Retrieval System)

本次版本上线了完整的电信网规网优智能语料检索系统，为专家提供高精度的专业知识检索服务，消除通用大模型的"幻觉"问题。

##### 1. 全量构建流水线

- **异构文档解析**：支持 Word (.docx)、PDF (.pdf)、PPT (.pptx) 及 Excel (.xlsx/.xls) 文件的批量转换
- **Docling 引擎**：高性能布局分析及 Markdown 转化，自动提取文档图片
- **Excel 标准化**：使用 Pandas 将 Sheet 记录转为标准 Markdown 表格，保留行列关系
- **全量重建策略**：构建时先清空索引，再执行解析、切片与入库，确保数据一致性
- **容错机制**：单个文件解析失败时记录日志并跳过，不中断全量构建

**新增 API：**
- `POST /api/corpus/build` - 触发完整语料构建流水线
- `GET /api/corpus/status` - 查询构建状态和索引统计

##### 2. 语义切片 (Semantic Chunking)

- **标题结构感知**：按 Markdown 标题层级（#、##、###）分割，保留语义完整性
- **段落级粒度**：大段落按 paragraph 边界继续切分，最大 1200 字符
- **重叠保留**：相邻块之间保留 100 字符重叠，避免语义断裂
- **元数据追踪**：每块包含源文件、标题路径、索引号、内容哈希、图片引用等信息

##### 3. 高精度检索 (High-Precision Retrieval)

- **FAISS 向量检索**：基于 Embedding 向量召回 Top-20 候选
- **BGE-Reranker 重排序**：远程 Reranker API 结合专家词表强制重排，输出 Top-3
- **专家词表增强**：自动检测查询中的专业术语，匹配文档中包含该术语的内容并给予 20% 分数加成
- **同义词扩展**：查询时自动扩展同义词，提升召回率
- **拒答机制**：重排序分数低于阈值（默认 0.3）时，明确返回"语料库中未找到相关准确依据"，拒绝臆断

**新增 Tool：**
- `search_corpus` - 语料检索工具，支持查询和返回引用链接

**新增配置项：**
- `RERANKER_MODEL` - Reranker 模型名称（默认：`bge-reranker-v2-m3`）
- `RERANKER_BASE_URL` - Reranker API 地址
- `RERANKER_API_KEY` - Reranker API 密钥
- `RERANKER_THRESHOLD` - 拒答分数阈值（默认：0.3）

##### 4. 专家治理入口 (Expert Glossary Management)

- **多格式支持**：JSON 和 CSV 格式的术语表/同义词映射表
- **动态加载**：支持上传新的术语表文件，系统自动热加载
- **词表管理**：查看所有术语表统计信息，删除不需要的术语表

**新增 API：**
- `GET /api/corpus/glossary` - 列出术语表文件和统计
- `POST /api/corpus/glossary/upload` - 上传术语表文件
- `DELETE /api/corpus/glossary/{filename}` - 删除术语表文件

**术语表格式示例（JSON）：**
```json
{
  "terms": [
    {"term": "弱覆盖", "definition": "RSRP低于-110dBm的覆盖区域"},
    {"term": "越区覆盖", "definition": "小区信号超出预期范围到其他小区"}
  ],
  "synonyms": {
    "参考信号接收功率": ["RSRP", "Reference Signal Received Power"],
    "信噪比": ["SINR", "Signal to Interference plus Noise Ratio"]
  }
}
```

##### 5. 前端语料查看器 (Corpus Viewer)

- **虚拟滚动预览**：支持 10MB+ 超大 Markdown 文件的流畅浏览
- **锚点跳转**：点击引用标签自动跳转至对应段落位置
- **关键词高亮**：自动高亮显示匹配查询关键词的内容
- **图片显示**：解析文档中的图片并保持相对位置
- **目录导航**：左侧标题树形导航，快速跳转到指定章节
- **分页加载**：懒加载内容，避免一次性渲染大量 DOM

**新增组件：**
- `CorpusViewer.tsx` - 语料文件查看器（分页滚动）
- `CorpusChunk.tsx` - 片段渲染器（关键词高亮+图片显示）
- `CorpusSidebar.tsx` - 标题导航树
- `GlossaryManager.tsx` - 专家词表上传/查看/删除管理界面
- `CorpusFileList.tsx` - 语料文件列表

**新增 API：**
- `GET /api/corpus/files` - 列出已解析的语料 Markdown 文件
- `GET /api/corpus/files/{id}` - 获取语料文件的分页内容
- `GET /api/corpus/files/{id}/meta` - 获取文件元数据和标题结构

##### 6. 消息引用集成 (Message Citation Integration)

- **引用链接**：消息中的语料引用可点击，右侧面板自动切换为语料查看器
- **上下文保留**：查看语料时保持当前对话上下文
- **快速返回**：一键返回对话面板

### 技术改进 (Technical Improvements)

#### 后端优化

- **模块化解析器**：独立的 DoclingParser 和 ExcelParser，易于扩展新的文件格式
- **Pipeline 单例**：`CorpusPipeline` 确保构建过程互斥，防止并发冲突
- **Glossary 热加载**：术语表更新后无需重启服务
- **Reranker 降级策略**：API 调用失败时自动降级为原始 FAISS 排序

#### 前端优化

- **Zustand 状态管理**：新增 `corpusStore` 管理语料查看器状态
- **React-Markdown 渲染**：安全渲染 Markdown 内容，支持自定义组件
- **响应式布局**：语料查看器适应不同屏幕尺寸

### 测试覆盖 (Test Coverage)

新增完整的单元测试套件，确保系统稳定性：

- **test_pipeline.py** - 语料构建流水线测试（190 行）
- **test_chunker.py** - 语义切片测试（183 行）
- **test_parsers.py** - 文档解析器测试（136 行）
- **test_reranker.py** - 重排序客户端测试（199 行）
- **test_glossary.py** - 术语表管理测试（212 行）
- **test_corpus_api.py** - 语料 API 测试（235 行）
- **test_knowledge_tools.py** - 知识工具测试（186 行）

所有单元测试使用 mock 设置，无需真实 LLM API 即可运行。

### 性能规格 (Performance Specs)

- **Top3 Precision**：≥ 80%（目标）
- **错误引用率**：≤ 8%（目标）
- **P95 查询延迟**：≤ 5s（目标）
- **拒答准确率**：≥ 95%（无证据不生成）

### 配置变更 (Configuration Changes)

新增环境变量：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `CORPUS_SOURCE_DIR` | `../corpus_source` | 源文档目录 |
| `CORPUS_MD_DIR` | `../corpus_md` | 解析后 Markdown 输出目录 |
| `CORPUS_IMAGE_DIR` | `../corpus_md/images` | 提取的图片目录 |
| `CORPUS_GLOSSARY_DIR` | `../corpus_md/glossary` | 术语表文件目录 |
| `EMBEDDING_MODEL` | `text-embedding-v3` | Embedding 模型名称 |
| `EMBEDDING_API_KEY` | `$LLM_API_KEY` | Embedding API 密钥 |
| `EMBEDDING_BASE_URL` | `$LLM_BASE_URL` | Embedding API 地址 |
| `RERANKER_MODEL` | `bge-reranker-v2-m3` | Reranker 模型名称 |
| `RERANKER_BASE_URL` | - | Reranker API 地址 |
| `RERANKER_API_KEY` | - | Reranker API 密钥 |
| `RERANKER_THRESHOLD` | `0.3` | 拒答分数阈值 |

### 依赖更新 (Dependency Updates)

新增 Python 依赖：
- `docling` - 文档解析引擎
- `pandas` - Excel 处理
- `openpyxl` - Excel 文件读写
- `httpx` - HTTP 客户端（Reranker API）

### 迁移指南 (Migration Guide)

升级到 1.1.0 版本后的操作步骤：

1. **安装新依赖**：
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. **配置 Reranker API**（可选）：
   ```bash
   # .env
   RERANKER_BASE_URL=https://your-reranker-api.com
   RERANKER_API_KEY=your-api-key
   RERANKER_MODEL=bge-reranker-v2-m3
   ```

3. **准备语料源文件**：
   ```bash
   mkdir -p corpus_source
   # 将 Word/PDF/PPT/Excel 文件放入 corpus_source/
   ```

4. **构建语料索引**：
   ```bash
   # 启动服务后
   curl -X POST http://localhost:8000/api/corpus/build
   ```

5. **上传专家术语表**（可选）：
   - 在前端 GlossaryManager 中上传 JSON/CSV 文件
   - 或直接放置到 `corpus_md/glossary/` 目录

### 已知问题 (Known Issues)

- **图片搜索**：不执行离线 OCR，图片搜索完全依赖 MD 上下文描述
- **增量构建**：当前仅支持全量重建，暂不支持增量更新
- **大型文件**：单个 Markdown 文件超过 50MB 可能出现性能问题

### 下个版本计划 (Roadmap)

- [ ] 增量构建支持（仅重新解析变更文件）
- [ ] 文档版本管理和历史回溯
- [ ] 多租户隔离和权限控制
- [ ] 语料统计和分析仪表盘

---

## Version 1.0.0 - Previous Release

### 初始功能

- 数字孪生场景管理
- 小区级/栅格级根因分析
- 优化仿真对比
- 术语检索工具
- 设计文档检索工具
- Agent 中间件系统（Skill、SubAgent、DataTable、ChartData、Suggestions、ContextEditing、MissingParams、HITL）
- SSE 流式响应
- 前端三栏布局（对话面板、输入区、任务面板）
