# WeChat-RAG — 项目知识索引

## 项目
RAG 智能问答系统，面向政策文档。两项目（国际杰青计划 + 科技部培训班），21 chunks。双前端（React + 微信小程序）。

## 架构（2026-06）
- LLM: DeepSeek V4 Flash (deepseek-chat)，HTTP API
- Embedding: 百炼 text-embedding-v4，HTTP API
- Reranker: 百炼 qwen3-rerank，HTTP API
- ES: Elasticsearch 8.17.1 + IK 中文分词，1GB JVM 堆
- 后端: FastAPI + uvicorn，port 6006
- 前端: React (rag-ui/) + 微信小程序 (miniprogram/)
- 部署: docker-compose（es + backend），代码 volume 挂载热更新
- 仓库: https://github.com/KafCaf/WeChat-RAG

## 命令
- 启动: `docker compose up -d`
- 重启（代码改动后）: `docker compose restart backend`
- API 测试: `curl http://localhost:6006/projects`
- 问答测试: `curl -X POST http://localhost:6006/chat -H "Content-Type: application/json" -d '{"message":"问题","project_name":"国际杰青计划","history":[],"top_k":5}'`
- 入库文档: `docker exec rag-backend python init_database.py`
- ES 管理: `python toolkit/es_inspect.py --index index_user_test`

## 准确度优化清单
1. ✅ RRF候选池 4→20，接入云端Reranker (qwen3-rerank)
2. ✅ BM25 中文分词 standard → ik_smart
3. ✅ Prompt 优化（few-shot + 幻觉约束 + 格式规范）
4. ✅ max_tokens 1024 → 2048
5. ✅ TSDocxSplitter 标题感知分块（培训班生效，杰青表格格式待适配）
6. ✅ 代码清理（去除 Gradio/torch/langchain/本地 LLM）
7. ❌ ES script_score 应改为 knn query
8. ❌ get_documents_with_ids 丢弃元数据
9. ❌ LLM API 无重试
10. ❌ 杰青文档表格格式需要专用分块策略

## 已废弃，勿用
- 交叉编码器（server/reranker.py 本地部分）— 已用云 API 替代
- Gradio 前端（app_demo.py, web.py）— 已删除
- 本地 LLM 推理（server/llm.py）— 已删除

## 部署
- 测试机: 华为云 Flexus 4核8G（月付 ¥180，短期测试）
- 推荐生产: 腾讯云轻量 2核4G（年付 ¥312）
- 更换服务器: git clone + 重新入库，ES 数据无需迁移

## 输出
生成文件放 /Users/cheyne/Downloads/
