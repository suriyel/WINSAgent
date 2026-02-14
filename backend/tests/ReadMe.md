| 测试文件                                                     | 测试数 | 覆盖模块                                                     |
| ------------------------------------------------------------ | ------ | ------------------------------------------------------------ |
| [test_chunker.py](vscode-webview://0gmp4ucqb0s47fh71691pajbubebjl1ap4uvpl4c4tm5fp5nmaii/backend/tests/test_chunker.py) | 16     | 语义切片器（heading 分割、段落切分、图片检测、content hash） |
| [test_parsers.py](vscode-webview://0gmp4ucqb0s47fh71691pajbubebjl1ap4uvpl4c4tm5fp5nmaii/backend/tests/test_parsers.py) | 12     | Excel 解析器（单/多 Sheet、空 Sheet、管道符转义、NaN 处理）  |
| [test_glossary.py](vscode-webview://0gmp4ucqb0s47fh71691pajbubebjl1ap4uvpl4c4tm5fp5nmaii/backend/tests/test_glossary.py) | 12     | 专家词表（JSON/CSV 加载、同义词扩展、术语匹配、reload）      |
| [test_reranker.py](vscode-webview://0gmp4ucqb0s47fh71691pajbubebjl1ap4uvpl4c4tm5fp5nmaii/backend/tests/test_reranker.py) | 6      | Reranker 客户端（API 调用/回退、glossary boost、阈值判断）   |
| [test_pipeline.py](vscode-webview://0gmp4ucqb0s47fh71691pajbubebjl1ap4uvpl4c4tm5fp5nmaii/backend/tests/test_pipeline.py) | 10     | 构建流水线（文件发现、构建流程、并发锁、get_chunks）         |
| [test_corpus_api.py](vscode-webview://0gmp4ucqb0s47fh71691pajbubebjl1ap4uvpl4c4tm5fp5nmaii/backend/tests/test_corpus_api.py) | 13     | API 路由（status/files/meta/glossary CRUD）                  |
| [test_knowledge_tools.py](vscode-webview://0gmp4ucqb0s47fh71691pajbubebjl1ap4uvpl4c4tm5fp5nmaii/backend/tests/test_knowledge_tools.py) | 7      | search_corpus 工具（完整检索链路、拒答、溯源格式）           |