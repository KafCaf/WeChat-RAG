import os
import time
import asyncio
import traceback
import httpx
import hashlib
import shutil
from typing import Optional
from fastapi import UploadFile, File, Form, HTTPException, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from elasticsearch import Elasticsearch

from utils import get_kb_path, list_files_from_folder, list_kbs_from_folder
from init_database import process_document
from retrievers.VectorRetriever import VectorRetrieval
from configs.model_configs import EMBED_CONFIG
from server.embedding import CloudEmbedModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware # 🌟 引入跨域中间件
import sqlite3
from pydantic import BaseModel
import bcrypt 
from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
app = FastAPI()

# 🌟 新增跨域配置，必须放在所有路由的最前面
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有域名访问
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有请求方法 (GET, POST等)
    allow_headers=["*"],  # 允许所有请求头
)
es_client = None
embed_model = None
retriever = None
http_client = None

# API Key 和 URL 均通过环境变量读取，不硬编码
# 阿里云百炼 DeepSeek LLM API (兼容 OpenAI 格式)
DASHSCOPE_LLM_URL = os.getenv("DASHSCOPE_LLM_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
TARGET_MODEL = os.getenv("TARGET_MODEL", "deepseek-v4-flash")
# 阿里云百炼 Embedding API
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_EMBED_URL = os.getenv("DASHSCOPE_EMBED_URL", "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding")
DASHSCOPE_EMBED_MODEL = os.getenv("DASHSCOPE_EMBED_MODEL", "text-embedding-v4")
# 阿里云百炼 Reranker API
DASHSCOPE_RERANK_URL = os.getenv("DASHSCOPE_RERANK_URL", "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank")
DASHSCOPE_RERANK_MODEL = os.getenv("DASHSCOPE_RERANK_MODEL", "qwen3-rerank")
ES_URL = os.getenv("ES_URL", "http://localhost:9200")
CURRENT_INDEX = os.getenv("ES_INDEX", "index_user_test")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global es_client, embed_model, retriever, http_client
    
    # 1. 初始化 Elasticsearch
    es_client = Elasticsearch(ES_URL)
    
    # 2. 使用云端 Embedding (百炼 text-embedding-v4)，无需本地 GPU
    embed_model = CloudEmbedModel()
    retriever = VectorRetrieval(embed_model, es_client=es_client)
    
    http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_keepalive_connections=200, max_connections=500),
        timeout=httpx.Timeout(60.0, connect=5.0) 
    )
    
    # ================= 系统冷启动预热 =================
    print("\n" + "="*50)
    print("[系统预热] 正在执行 Dummy Request 消除冷启动开销...")
    
    try:
        # [预热 1]: 激活 Elasticsearch 连接与缓存池
        print("  -> 1/3 预热 Elasticsearch 索引与 I/O 缓存...")
        start_t = time.time()
        if es_client.ping():
            _ = es_client.search(index=CURRENT_INDEX, body={"query": {"match_all": {}}, "size": 1}, ignore=[400, 404])
        print(f"     完成，耗时: {time.time() - start_t:.2f}s")

        # [预热 2]: 激活云端 Embedding API 长连接 (百炼)
        print("  -> 2/3 预热云端 Embedding API 连接...")
        start_t = time.time()
        _ = embed_model.encode(["预热指令"], return_dense=True, return_sparse=False, return_colbert_vecs=False)
        print(f"     完成，耗时: {time.time() - start_t:.2f}s")

        # [预热 3]: 激活 DeepSeek API 长连接通道
        print("  -> 3/3 预热 DeepSeek LLM API 网络长连接通道...")
        start_t = time.time()
        dummy_payload = {
            "model": TARGET_MODEL,
            "messages": [{"role": "system", "content": "1"}],
            "max_tokens": 1
        }
        headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}", "Content-Type": "application/json"}
        
        _ = await asyncio.wait_for(
            http_client.post(DASHSCOPE_LLM_URL, json=dummy_payload, headers=headers),
            timeout=10.0
        )
        print(f"     完成，耗时: {time.time() - start_t:.2f}s")

        print("[系统预热] 全部预热完成！")
        print("="*50 + "\n")

    except Exception as e:
        print(f"[系统预热] 预热过程遇到非致命异常，跳过预热: {e}")
        print("="*50 + "\n")

    except Exception as e:
        # 预热失败不能影响主程序启动，直接捕获异常
        print(f"[系统预热] 预热过程遇到非致命异常，跳过预热: {e}")
    # =====================================================================
    
    yield
    
    # 清理逻辑
    await http_client.aclose()
    if es_client:
        es_client.close()

app = FastAPI(title="RAG API Server (Cloud LLM Version)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    project_name: Optional[str] = None
    history: list = []
    top_k: int = 15
    temperature: float = 0.01
    conversation_id: Optional[int] = None
    token: Optional[str] = ""

async def chat_and_rag(request: ChatRequest):
    try:
        loop = asyncio.get_running_loop()

        # 轻量同义词映射（0 API 调用，纯本地）
        SYNONYM_MAP = {
            "吃住": "生活开支 住房租赁 食宿",
            "工资": "资助经费 资助额度 经费",
            "多少钱": "资助额度 经费标准 费用",
            "相关通知": "",
            "相关信息": "",
            "有哪些": "",
        }
        query = request.message
        for k, v in SYNONYM_MAP.items():
            if k in query:
                query = f"{query} {v}"
        query = query.strip()

        start_retrieval_time = time.time()
        search_result = await loop.run_in_executor(
            None,
            retriever.search_rrf, 
            CURRENT_INDEX, 
            query,
            40,
            request.top_k, 
            request.project_name
        )
        retrieval_time = time.time() - start_retrieval_time
        
        if isinstance(search_result, tuple) and len(search_result) == 2:
            docs, scores = search_result
        else:
            docs = search_result
            
        context_list = []
        if docs:
            for doc in docs:
                content = doc.get('content') or doc.get('page_content') or doc.get('text') or str(doc) if isinstance(doc, dict) else str(doc)
                context_list.append(content)
            context = "\n---\n".join(context_list)
        else:
            context = "未能在知识库中找到相关背景知识。"
        
        print("\n" + "==="*10 + " 喂给大模型的知识切片长这样 " + "==="*10)
        print(context)
        print("==="*30 + "\n")

        system_prompt = f"""你是政策文档问答引擎。根据【背景知识】回答用户问题。

【判断逻辑】：
1. 背景知识涵盖答案 → 直接回答。
2. 背景知识部分相关（同义词、近义表述）→ 提取相关部分并注明"背景知识中未直接提及该措辞，以下是相关内容"。
3. 背景知识完全无关 → 输出"参考信息中未提及。"（仅此一句）。

【输出格式】：
- 直接问答：一句话结论。
- 摘要/概括：编号列表，覆盖背景知识中所有相关方面。
- 新旧对比：先结论，再分别简述旧版和新版要求。不标注条款号（如第五条、第十三条等）。
- 禁止：以"根据背景知识""以下是"开头、长篇引用。

【背景知识】:
{context}"""
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # 只保留最近 5 轮，跳过无用的"未提及"回复
        for user_msg, bot_msg in request.history[-5:]:
            clean_bot_msg = bot_msg.split("参考来源：")[0].strip() if bot_msg else ""
            if "参考信息中未提及" not in clean_bot_msg:
                messages.append({"role": "user", "content": user_msg})
                messages.append({"role": "assistant", "content": clean_bot_msg})
            
        messages.append({"role": "user", "content": request.message})
        
        payload = {
            "model": TARGET_MODEL,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": 2048,
            "stop": ["<|im_end|>"] 
        }
        
        headers = {
            "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # 优化项2：记录 LLM 请求耗时
        start_llm_time = time.time()
        response = await http_client.post(DASHSCOPE_LLM_URL, json=payload, headers=headers)
        llm_time = time.time() - start_llm_time
        
        print(f"[性能监控] 检索耗时: {retrieval_time:.2f}s | LLM API耗时: {llm_time:.2f}s")
        
        if response.status_code != 200:
            error_msg = f"DashScope API 调用失败，HTTP状态码: {response.status_code}, 报文: {response.text}"
            print(error_msg)
            raise HTTPException(status_code=502, detail="外部大模型服务网关异常。")
            
        result_json = response.json()
        raw_answer = result_json["choices"][0]["message"]["content"].strip()
        full_answer = raw_answer

        # 存储消息
        conv_id = request.conversation_id
        if request.token and request.token.startswith("token_"):
            username = request.token[6:]
            if not conv_id:
                title = request.message[:20] + ("..." if len(request.message) > 20 else "")
                conv_id = get_or_create_conversation(username, request.project_name, title)
            conn = sqlite3.connect("database.db")
            c = conn.cursor()
            if request.project_name:
                c.execute("UPDATE conversations SET project_name=? WHERE id=?", (request.project_name, conv_id))
            c.execute("INSERT INTO messages (conversation_id, role, content) VALUES (?, 'user', ?)", (conv_id, request.message))
            c.execute("INSERT INTO messages (conversation_id, role, content) VALUES (?, 'assistant', ?)", (conv_id, full_answer))
            conn.commit()
            conn.close()

        return {"answer": full_answer, "conversation_id": conv_id}

    except HTTPException:
        raise
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"RAG 流水线内部异常:\n{error_details}")
        raise HTTPException(status_code=500, detail="系统内部流转或外部网络异常。")

@app.post('/chat')
async def chat_endpoint(request: ChatRequest):
    return await chat_and_rag(request)

@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...), 
    project_name: str = Form(...) 
):
    try:
        # --- 1. 读取文件并执行物理大小拦截 ---
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 限制为 10MB
        file_content = await file.read()
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400, 
                detail=f"文件过大（{len(file_content) / 1024 / 1024:.2f}MB）。为了保护服务器算力，单次上传请限制在 10MB 以内。"
            )

        # --- 2. 计算文件的 MD5 数字指纹 ---
        file_md5 = hashlib.md5(file_content).hexdigest()
        print(f"[文件校验] 收到文件: {file.filename}, MD5指纹: {file_md5}")

        # --- 3. 极速查重：指纹匹配则直接触发“秒传” ---
        loop = asyncio.get_running_loop()
        is_duplicate = await loop.run_in_executor(
            None, 
            retriever.check_hash_exists, 
            CURRENT_INDEX, 
            file_md5, 
            project_name
        )
        
        if is_duplicate:
            return {
                "status": "success", 
                "message": f"文件内容与已有文档一致（MD5: {file_md5[:8]}），跳过入库。"
            }

        # --- 4. 正常保存文件到本地 ---
        project_dir = get_kb_path(project_name)
        os.makedirs(project_dir, exist_ok=True)
        file_path = os.path.join(project_dir, file.filename)
        
        with open(file_path, "wb") as f:
            f.write(file_content) # 直接使用刚才读取在内存里的 file_content
            
        # --- 5. 解析文件并切片 ---
        chunks = await loop.run_in_executor(None, process_document, file_path)
        
        if chunks is None or not chunks.get("text"):
            ext_hint = os.path.splitext(file.filename)[1].lower()
            if ext_hint == '.pdf':
                detail = "PDF 文件无法提取文本内容（可能为扫描件或图片型 PDF，请上传可选中文字的 PDF 或转换为 docx 格式）。"
            else:
                detail = "文件解析失败、格式不支持或内容为空。"
            raise HTTPException(status_code=400, detail=detail)
            
        chunks["project_name"] = project_name 
        chunks["file_hash"] = file_md5 # 🌟 将数字指纹绑定到这一批切片元数据上
        
        # --- 6. 热更新处理：清理旧版本切片 ---
        # 如果走到这里，说明内容不一样，但可能文件名一样（用户修改后重新上传）
        await loop.run_in_executor(
            None, 
            retriever.delete_file_chunks, 
            CURRENT_INDEX, 
            chunks["filename"], 
            project_name
        )
        
        # --- 7. 增量追加写入 Elasticsearch ---
        await loop.run_in_executor(None, retriever.build_index, CURRENT_INDEX, chunks)
        
        return {
            "status": "success", 
            "message": f"文档 {file.filename} 解析与索引构建完成，已安全入库。"
        }
    except HTTPException:
        raise
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"上传入库异常:\n{error_details}")
        raise HTTPException(status_code=500, detail=f"文件处理管线崩溃: {str(e)}")

@app.get("/projects")
async def get_project_list():
    try:
        kb_list = list_kbs_from_folder()
        final_list = ["全部项目 (全局搜索)"] + kb_list
        return {"status": "success", "projects": final_list}
    except Exception as e:
        return {"status": "error", "projects": ["全部项目 (全局搜索)"]}
# 🌟 新增：用户系统与数据库逻辑
# ==========================================



# 2. 初始化 SQLite 数据库 (如果没有 database.db 文件，会自动创建)
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    # 创建一个 users 表，包含 id, 用户名, 加密后的密码
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            title TEXT DEFAULT '新对话',
            project_name TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    # 兼容旧表：如果 project_name 列不存在则添加
    try:
        cursor.execute("ALTER TABLE conversations ADD COLUMN project_name TEXT DEFAULT NULL")
    except:
        pass
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
    """)
    conn.commit()
    conn.close()

# 启动时运行建表
init_db()

# 3. 定义前端传过来的数据格式
class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

# 4. 注册接口
@app.post("/register")
def register_api(user: UserCreate):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # 检查用户名是否已存在
    cursor.execute("SELECT * FROM users WHERE username=?", (user.username,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="该用户名已被注册")
    
    # 对密码进行哈希加密
   # 🌟 原生 bcrypt 加密：先转成 bytes，加盐哈希后，再转回字符串存入数据库
    hashed_bytes = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
    hashed_pwd = hashed_bytes.decode('utf-8')
    
    # 存入数据库
    cursor.execute("INSERT INTO users (username, hashed_password) VALUES (?, ?)", (user.username, hashed_pwd))
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": f"用户 {user.username} 注册成功"}

# 5. 登录接口
@app.post("/login")
def login_api(user: UserLogin):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # 查找用户
    cursor.execute("SELECT hashed_password FROM users WHERE username=?", (user.username,))
    record = cursor.fetchone()
    conn.close()
    
    if not record:
        raise HTTPException(status_code=401, detail="用户不存在")
    
    # 核对密码
    # 🌟 原生 bcrypt 验证：将用户输入的密码和数据库里的密码双双转为 bytes 进行安全核对
    # 核对密码
    if not bcrypt.checkpw(user.password.encode('utf-8'), record[0].encode('utf-8')):
        raise HTTPException(status_code=401, detail="密码错误")
        
    # 👇 给 React 发一个凭证
    fake_token = f"token_{user.username}" 
    return {"status": "success", "message": "登录成功", "username": user.username, "token": fake_token}

# ==================== 会话管理 ====================

def get_user_from_token(token: str) -> str:
    """从 token 提取用户名"""
    if token and token.startswith("token_"):
        return token[6:]
    raise HTTPException(status_code=401, detail="未登录")

def get_or_create_conversation(username: str, project_name: str = None, title: str = "新对话") -> int:
    """获取用户最近会话，没有则创建"""
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    if project_name:
        c.execute("SELECT id FROM conversations WHERE username=? AND project_name=? ORDER BY id DESC LIMIT 1", (username, project_name))
    else:
        c.execute("SELECT id FROM conversations WHERE username=? ORDER BY id DESC LIMIT 1", (username,))
    row = c.fetchone()
    if row:
        conv_id = row[0]
    else:
        c.execute("INSERT INTO conversations (username, title, project_name) VALUES (?, ?, ?)", (username, title, project_name))
        conn.commit()
        conv_id = c.lastrowid
    conn.close()
    return conv_id

class ConversationCreate(BaseModel):
    title: str = "新对话"
    project_name: Optional[str] = None

@app.get("/conversations")
async def list_conversations(token: str = "", project_name: str = ""):
    username = get_user_from_token(token)
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    if project_name:
        c.execute("SELECT id, title, created_at, project_name FROM conversations WHERE username=? AND project_name=? ORDER BY id DESC", (username, project_name))
    else:
        c.execute("SELECT id, title, created_at, project_name FROM conversations WHERE username=? ORDER BY id DESC", (username,))
    rows = c.fetchall()
    conn.close()
    return {"conversations": [{"id": r[0], "title": r[1], "created_at": r[2], "project_name": r[3]} for r in rows]}

@app.post("/conversations")
async def create_conversation(data: ConversationCreate, token: str = ""):
    username = get_user_from_token(token)
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("INSERT INTO conversations (username, title, project_name) VALUES (?, ?, ?)", (username, data.title, data.project_name))
    conn.commit()
    conv_id = c.lastrowid
    conn.close()
    return {"status": "success", "id": conv_id, "project_name": data.project_name}

@app.get("/conversations/{conv_id}")
async def get_conversation(conv_id: int, token: str = ""):
    username = get_user_from_token(token)
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT id FROM conversations WHERE id=? AND username=?", (conv_id, username))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="会话不存在")
    c.execute("SELECT role, content, created_at FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,))
    rows = c.fetchall()
    history = []
    for r in rows:
        history.append({"role": r[0], "content": r[1], "time": r[2]})
    # 获取会话的项目名
    c.execute("SELECT project_name FROM conversations WHERE id=?", (conv_id,))
    proj_row = c.fetchone()
    conn.close()
    return {"history": history, "project_name": proj_row[0] if proj_row else None}

@app.patch("/conversations/{conv_id}")
async def rename_conversation(conv_id: int, data: ConversationCreate, token: str = ""):
    username = get_user_from_token(token)
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT id FROM conversations WHERE id=? AND username=?", (conv_id, username))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="会话不存在")
    c.execute("UPDATE conversations SET title=? WHERE id=?", (data.title, conv_id))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: int, token: str = ""):
    username = get_user_from_token(token)
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT id FROM conversations WHERE id=? AND username=?", (conv_id, username))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="会话不存在")
    c.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
    c.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "会话已删除"}

# ==================== 推荐问题 ====================

@app.get("/suggest-questions")
async def suggest_questions(project_name: str):
    """根据项目内容生成 3 个推荐问题，优先返回缓存"""
    # 先查 ES 拿几个 chunk 样本
    try:
        es_q = {"query": {"term": {"project_name": project_name}}, "size": 3}
        res = await asyncio.get_running_loop().run_in_executor(
            None, lambda: es_client.search(index=CURRENT_INDEX, body=es_q)
        )
        hits = res["hits"]["hits"]
        if not hits:
            return {"status": "success", "questions": ["请先上传文档到该项目"]}
        
        samples = [h["_source"]["content"][:500] for h in hits]
        context = "\n---\n".join(samples)
        
        prompt = f"根据以下文档片段，生成 3 个用户最可能问的问题。只输出问题，每行一个，不要编号，不要任何其他文字：\n\n{context}"
        payload = {
            "model": TARGET_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "temperature": 0.7
        }
        headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}", "Content-Type": "application/json"}
        api_resp = await http_client.post(DASHSCOPE_LLM_URL, json=payload, headers=headers)
        
        if api_resp.status_code == 200:
            raw = api_resp.json()["choices"][0]["message"]["content"].strip()
            questions = [q.strip().lstrip("-0123456789. ") for q in raw.split("\n") if q.strip()][:3]
        else:
            questions = ["资助期限最长多久？", "申请条件是什么？", "需要什么材料？"]
        
        return {"status": "success", "questions": questions}
    except Exception:
        return {"status": "success", "questions": ["资助期限最长多久？", "申请条件是什么？", "需要什么材料？"]}

# ==================== 知识库管理 ====================

@app.get("/files")
def list_files(project_name: str):
    """获取指定项目下的文档列表"""
    try:
        files = list_files_from_folder(project_name)
        return {"status": "success", "files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")

@app.delete("/files")
async def delete_file(filename: str, project_name: str, token: str = ""):
    """删除指定文档：验证用户身份后，从 ES 和磁盘中彻底清除"""
    username = get_user_from_token(token)
    
    # 删除磁盘文件
    file_path = os.path.join(get_kb_path(project_name), filename)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[删除] 已删除磁盘文件: {file_path}")
    except Exception as e:
        print(f"[删除] 磁盘文件删除失败: {e}")
    
    # 删除 ES chunks
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, retriever.delete_file_chunks, CURRENT_INDEX, str(file_path), project_name
    )
    
    return {"status": "success", "message": f"文件 {filename} 已删除"}


@app.delete("/projects/{project_name}")
async def delete_project(project_name: str, token: str = ""):
    """删除整个项目及其下所有文档"""
    username = get_user_from_token(token)
    
    # 1. 删除 ES 中该项目所有 chunks
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, retriever.delete_file_chunks, CURRENT_INDEX, "*", project_name
    )
    
    # 2. 删除磁盘上的知识库目录
    kb_path = get_kb_path(project_name)
    if os.path.exists(kb_path):
        shutil.rmtree(kb_path)
        print(f"[删除] 已删除项目目录: {kb_path}")
    
    # 3. 删除 SQLite 中该项目的会话记录
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE project_name=?)", (project_name,))
    c.execute("DELETE FROM conversations WHERE project_name=?", (project_name,))
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": f"项目 {project_name} 及其所有文档、会话已删除"}

# 1. 挂载静态资源（CSS, JS, 图片等），让浏览器能找到网页的“衣服”
_static_dir = "rag-ui/dist/assets"
if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=_static_dir), name="assets")
else:
    print(f"[WARN] React 前端未构建 ('{_static_dir}' 不存在)，跳过静态文件挂载")

# 2. 访问根路径 "/" 时，直接把刚才打包好的 index.html 丢给浏览器看
@app.get("/")
async def read_index():
    if os.path.isfile("rag-ui/dist/index.html"):
        return FileResponse("rag-ui/dist/index.html")
    return {"status": "ok", "message": "RAG API is running. React frontend not deployed."}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=6006, workers=1)






