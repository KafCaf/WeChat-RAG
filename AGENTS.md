# WeChat-RAG — 项目知识索引

## 项目
RAG 智能问答系统，面向政策文档（国际杰青计划管理办法等）。56 道 QA 测试题。双前端（React + 微信小程序）。

## 架构（2025-06 已改造）
- LLM: DeepSeek V4 Flash (deepseek-chat)，HTTP API
- Embedding: 百炼 text-embedding-v4，HTTP API（替代本地 BGE-M3）
- Reranker: 百炼 gte-rerank，HTTP API（替代 ColBERT）
- ES: Elasticsearch 8.17.1，1GB JVM 堆（-Xmx1g）
- 后端: FastAPI + uvicorn，port 6006
- 前端: React (rag-ui/) + 微信小程序 (miniprogram/)
- 部署: docker-compose（es + backend 两个服务）
- 仓库: https://github.com/KafCaf/WeChat-RAG

## 命令
- 启动: `docker compose up -d`
- API 测试: `curl http://localhost:6006/projects`
- 评估: `python auto_eval.py`
- ES 管理: `python toolkit/es_inspect.py --index index_user_test`

## 准确度优化清单
1. ✅ RRF候选池 4→20，接入云端Reranker
2. ❌ 交叉编码器未接入（server/reranker.py）
3. ❌ 固定分块切条款（init_database.py L135），TSdocx_splitter 未集成
4. ❌ BM25 中文分词用 standard tokenizer
5. ❌ get_documents_with_ids 丢弃元数据
6. ❌ Prompt 无 few-shot
7. ❌ ES script_score 应改为 knn query
8. ❌ max_tokens=1024 可能截断
9. ❌ LLM API 无重试

## 成本
- 推荐服务器: 腾讯云轻量 2核4G（年付 ¥312）
- DeepSeek API: 年约 ¥43
- 百炼 API: 月约 ¥15
- 3个月总约 ¥250，半年约 ¥510

## 输出
生成文件放 /Users/cheyne/Downloads/
