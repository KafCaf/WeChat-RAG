# WeChat-RAG — 项目知识索引

## 项目
RAG 智能问答系统，面向政策文档。三项目（国际杰青计划 + 科技部培训班 + 宿舍选房通知），57 chunks。双前端（React + 微信小程序）。

## 架构
- LLM: 阿里云百炼 DeepSeek V4 Flash (deepseek-v4-flash)，HTTP API
- Embedding: 百炼 text-embedding-v4，HTTP API
- Reranker: 百炼 qwen3-rerank，HTTP API
- ES: Elasticsearch 8.17.1 + IK 中文分词 (ik_smart)，1GB JVM 堆
- 后端: FastAPI + uvicorn，port 6006（仅内网）
- 前端: React (rag-ui/) — 已部署，标题"智能问答系统（测试）"
- 小程序: miniprogram/ — AppID wx3abc7e5d77ee3124，已备案通过
- 反向代理: Nginx + Let's Encrypt HTTPS → 内网 6006
- 部署: docker-compose（es + backend），代码 volume 挂载热更新
- 仓库: https://github.com/KafCaf/WeChat-RAG

## 部署
- 服务器: 阿里云轻量 2核4G，年付 ¥379，IP 139.196.192.248
- 域名: rag-ai.top（ICP 备案已通过）
- 外网: https://rag-ai.top/（安全组 22/80/443）
- 热更新: 改服务器文件 → `docker compose restart backend` → 10秒生效
- ⚠️ 不要 `docker compose down` — ES 容器重建会丢失 IK 插件，需重装
- 开发账号: `devuser`（密码 rag2026dev），可操作 Docker、Nginx

## 命令
- 启动: `docker compose up -d`
- 重启后端: `docker compose restart backend`
- API 测试: `curl https://rag-ai.top/projects`
- 问答测试: `curl -X POST https://rag-ai.top/chat -H "Content-Type: application/json" -d '{"message":"问题","project_name":"国际杰青计划","history":[],"top_k":5}'`
- 入库文档: `docker exec rag-backend python init_database.py`
- ES 管理: `python toolkit/es_inspect.py --index index_user_test`
- SSL 续期: `certbot renew --dry-run`
- 安装 IK 插件: `docker exec rag-es elasticsearch-plugin install --batch https://get.infini.cloud/elasticsearch/analysis-ik/8.17.1`

## 知识库
| 项目 | 文档 | Chunks |
|---|---|---|
| 国际杰青计划 | 管理办法修改草案（17→25 年对照）.docx | 42 |
| 科技部培训班 | 管理办法（修订稿）.docx | 7 |
| 宿舍选房通知 | PDF（7页，含学硕/专硕名单） | 8 |

## API 接口
| 接口 | 方法 | 说明 |
|---|---|---|
| /chat | POST | 问答 |
| /upload | POST | 文件上传 |
| /projects | GET | 项目列表 |
| /projects/{name} | PATCH | 项目改名（同步迁移 ES） |
| /projects/{name} | DELETE | 删除项目 |
| /files | GET | 文档列表 |
| /files | DELETE | 删除文档 |
| /register | POST | 注册 |
| /login | POST | 登录 |
| /wx-login | POST | 微信静默登录 |
| /conversations | GET/POST | 会话管理 |
| /conversations/{id} | GET/PATCH/DELETE | 单个会话 |

## 核心功能
- RAG 问答: 百炼 DeepSeek V4 Flash + 百炼 embedding + qwen3-rerank
- IK 中文分词: ES ik_smart
- 项目隔离: 按 project_name 过滤检索 + 会话绑定项目
- 会话管理: 自动创建、改名、删除、项目分组
- 文件上传: 支持 .pdf/.docx/.txt/.md，MD5 查重
- 用户认证: 注册/登录（SQLite + bcrypt）+ 微信静默登录
- Markdown 渲染: react-markdown
- Prompt: 判断树 + 禁止幻觉 + 同义词映射（已清理空白映射）
- 知识库管理: 文档/项目删除（Web + 小程序双端）
- LLM 重试: 3 次指数退避

## 协作

### 分支保护
- main 分支已设保护，必须通过 Pull Request 合并
- 协作者推分支 → 提 PR → 仓库管理员合并

### 小程序发布
- 开发者工具 → 上传 → mp.weixin.qq.com → 选为体验版/提交审核
- 注意：不要编译后未测试直接上传

## 已废弃，勿用
- 交叉编码器（server/reranker.py 本地部分）
- Gradio 前端（app_demo.py, web.py）
- 本地 LLM 推理（server/llm.py）
- DeepSeek 官方 API（已切百炼）
- suggest-questions 接口（超时体验差，已删除）
- navigation-bar 组件（小程序用自定义导航栏）

## Git 推送
- 作者 SSH 在某些 VPN 节点被 GitHub 断开，更换节点可解决
- Agent 沙箱环境推送不稳定，需要时用户手动 `git push`

## 输出
生成文件放 /Users/cheyne/Downloads/
