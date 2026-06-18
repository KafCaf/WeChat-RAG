# WeChat-RAG — 项目知识索引

## 项目
RAG 智能问答系统，面向政策文档。三项目（国际杰青计划 + 科技部培训班 + 选房通知），69 chunks。双前端（React + 微信小程序）。

## 架构
- LLM: 阿里云百炼 DeepSeek V4 Flash (deepseek-v4-flash)，HTTP API
- Embedding: 百炼 text-embedding-v4，HTTP API
- Reranker: 百炼 qwen3-rerank，HTTP API
- ES: Elasticsearch 8.17.1 + IK 中文分词 (ik_smart)，1GB JVM 堆
- 后端: FastAPI + uvicorn，port 6006
- 前端: React (rag-ui/) — 已部署到服务器，标题"智能问答系统（测试）"
- 部署: docker-compose（es + backend），代码 volume 挂载热更新
- 仓库: https://github.com/KafCaf/WeChat-RAG

## 部署
- 当前: 华为云 Flexus 4核8G，上海，Ubuntu 24.04，月付 ¥180
- 外网: http://123.60.19.173:6006/（安全组放通 22 + 6006）
- 推荐生产: 腾讯云轻量 2核4G（年付 ¥312），月底评估迁移
- 更换服务器: git clone + 重新入库，ES 数据无需迁移
- 代码热更新: 改服务器文件 → `docker compose restart backend` → 10秒生效

## 命令
- 启动: `docker compose up -d`
- 重启（代码改动后）: `docker compose restart backend`
- API 测试: `curl http://localhost:6006/projects`
- 问答测试: `curl -X POST http://localhost:6006/chat -H "Content-Type: application/json" -d '{"message":"问题","project_name":"国际杰青计划","history":[],"top_k":5}'`
- 入库文档: `docker exec rag-backend python init_database.py`
- ES 管理: `python toolkit/es_inspect.py --index index_user_test`

## 知识库
| 项目 | 文档 | Chunks |
|---|---|---|
| 国际杰青计划 | 管理办法修改草案（17→25 年对照）.docx | 54 |
| 科技部培训班 | 管理办法（修订稿）.docx | 7 |
| 选房通知 | PDF（7页，含学硕/专硕名单） | 8 |

## 核心功能
- RAG 问答: DeepSeek V4 Flash + 百炼 embedding + qwen3-rerank
- IK 中文分词: ES ik_smart
- 项目隔离: 按 project_name 过滤检索 + 会话绑定项目
- 会话管理: 自动创建、改名、删除、项目分组
- 文件上传: 支持 .docx/.pdf/.txt/.xlsx
- 用户认证: 注册/登录（SQLite + bcrypt）
- Markdown 渲染: react-markdown
- 查重: MD5 哈希，重复文件跳过入库
- Prompt: 判断树（涵盖/部分/无关）+ 禁止"根据背景知识"开头 + 同义词映射

## 已完成优化
1. ✅ RRF候选池 4→20，接入云端Reranker (qwen3-rerank)
2. ✅ BM25 中文分词 standard → ik_smart
3. ✅ Prompt 优化（few-shot + 幻觉约束 + 格式规范）
4. ✅ max_tokens 1024 → 2048
5. ✅ TSDocxSplitter 标题感知分块
6. ✅ 代码清理（去除 Gradio/torch/langchain/本地 LLM）
7. ✅ get_documents_with_ids 保留元数据
8. ✅ React 前端部署上线

## 待优化
| 项 | 优先级 | 说明 |
|---|---|---|
| LLM API 重试 | 中 | DeepSeek 偶发超时抛 500 |
| ES script_score → knn query | 低 | 69 chunks 无感 |
| 表格格式通用适配 | 低 | 当前 54 chunks 够用 |
| 小程序上线 | 需域名+HTTPS | — |

## 已废弃，勿用
- 交叉编码器（server/reranker.py 本地部分）— 已用云 API 替代
- Gradio 前端（app_demo.py, web.py）— 已删除
- 本地 LLM 推理（server/llm.py）— 已删除

## 输出
生成文件放 /Users/cheyne/Downloads/
