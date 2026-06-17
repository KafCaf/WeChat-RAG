import os
import time
import asyncio
import traceback
import httpx
import hashlib
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
# DeepSeek API (兼容 OpenAI 格式)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
TARGET_MODEL = os.getenv("TARGET_MODEL", "deepseek-chat")  # DeepSeek V4 Flash
# 阿里云百炼 Embedding API
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_EMBED_URL = os.getenv("DASHSCOPE_EMBED_URL", "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding")
DASHSCOPE_EMBED_MODEL = os.getenv("DASHSCOPE_EMBED_MODEL", "text-embedding-v4")
# 阿里云百炼 Reranker API
DASHSCOPE_RERANK_URL = os.getenv("DASHSCOPE_RERANK_URL", "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank")
DASHSCOPE_RERANK_MODEL = os.getenv("DASHSCOPE_RERANK_MODEL", "gte-rerank")
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
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        
        _ = await asyncio.wait_for(
            http_client.post(DEEPSEEK_API_URL, json=dummy_payload, headers=headers),
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
    top_k: int = 5
    temperature: float = 0.01 

async def chat_and_rag(request: ChatRequest):
    try:
        loop = asyncio.get_running_loop()

#         expansion_prompt = f"""请分析以下用户的搜索查询，生成3个同义搜索词或相关查询的扩展组合（涵盖口语、专业术语等），以帮助搜索引擎召回更多相关文档。
# 直接输出这3个查询词，使用“|”符号分隔，不要输出任何其他解释性文字。
# 用户查询：{request.message}"""

# 1. 提取上一轮的对话上下文，用于指代消解
        context_hint = ""
        if request.history:
            # 只取最后一轮对话提供背景
            last_user, last_bot = request.history[-1]
            # 截断太长的机器回复，保留前200字即可
            short_bot = last_bot[:200] + "..." if len(last_bot) > 200 else last_bot
            context_hint = f"【上一轮对话参考】\n用户问：{last_user}\n系统答：{short_bot}\n\n"

        # 2. 将上下文拼接到扩展提示词中
        expansion_prompt = f"""请结合【上一轮对话参考】（如果有），分析用户的【最新查询】。
如果最新查询包含代词（如“上面”、“这个”、“那条”），请结合参考对话将其还原为完整的搜索意图。
生成3个同义搜索词或相关查询的扩展组合，以帮助搜索引擎召回更多相关文档。
直接输出这3个查询词，使用“|”符号分隔，不要输出任何其他解释性文字。

{context_hint}【最新查询】：{request.message}"""

        expansion_payload = {
            "model": TARGET_MODEL,
            "messages": [{"role": "user", "content": expansion_prompt}],
            "temperature": 0.3, # 稍微给点温度，增加发散性
            "max_tokens": 100
        }
        
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        
        # 异步调用大模型进行扩展
        exp_response = await http_client.post(DEEPSEEK_API_URL, json=expansion_payload, headers=headers)
        if exp_response.status_code == 200:
            expanded_text = exp_response.json()["choices"][0]["message"]["content"].strip()
            # 将原始问题与扩展词拼接，形成更丰富的召回 Query
            enhanced_query = f"{request.message} | {expanded_text}"
        else:
            # 如果扩展失败，平滑退化为使用原始请求
            enhanced_query = request.message
            
        print(f"[意图扩展] 原始: {request.message} -> 扩展后: {enhanced_query}")
        
        # 优化项2：记录检索阶段耗时
        start_retrieval_time = time.time()
        search_result = await loop.run_in_executor(
            None,
            retriever.search_rrf, 
            CURRENT_INDEX, 
            enhanced_query, # <--- 这里！把 request.message 替换为刚刚生成的 enhanced_query
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

        system_prompt = f"""你是一个极其严谨的政策文档问答引擎。

【绝对纪律】：
1. 你的唯一任务是从【背景知识】中提取答案，绝对禁止脱离背景知识进行任何联想、扩写或编造。
2. 如果背景知识中未涵盖答案，直接输出："参考信息中未提及"（不得加任何解释）。
3. 如果背景知识同时包含旧版和新版信息（如【2017年管理办法】和【2025年修改稿】），优先输出新版，并说明与旧版的区别。
4. 数字、日期、金额必须原样摘抄，不得改写。
5. 回答应简洁直接，先给结论，再展开依据。

【正确示例】:
用户：资助期限最长多久？
背景知识：【2025年修改稿】第十三条 项目执行周期分为3个月、6个月、12个月三类。
回答：根据【2025年修改稿】第十三条，最长12个月。项目执行周期分三类：3个月、6个月、12个月。

【不确定示例】:
用户：申请人是否需要提供体检报告？
背景知识：【2017年管理办法】第三条 申请人应具有博士学位或5年以上科研工作经历。
回答：参考信息中未提及。

【提取要求】：
- 如果条款包含多个并列条件（如（一）（二）（三）），全部提取。
- 如果条件序号不连续（如只有（一）（三）但缺（二）），只输出已有的，末尾加注："（注：受限于检索到的参考片段，该条款的其余部分缺失，未能在回答中完整呈现。）"
- 禁止自行编造补全缺失的条件。

【背景知识】:
{context}"""
        
        messages = [{"role": "system", "content": system_prompt}]
        
        for user_msg, bot_msg in request.history[-3:]:
            clean_bot_msg = bot_msg.split("参考来源：")[0].strip() if bot_msg else ""
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
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # 优化项2：记录 LLM 请求耗时
        start_llm_time = time.time()
        response = await http_client.post(DEEPSEEK_API_URL, json=payload, headers=headers)
        llm_time = time.time() - start_llm_time
        
        print(f"[性能监控] 检索耗时: {retrieval_time:.2f}s | LLM API耗时: {llm_time:.2f}s")
        
        if response.status_code != 200:
            error_msg = f"DashScope API 调用失败，HTTP状态码: {response.status_code}, 报文: {response.text}"
            print(error_msg)
            raise HTTPException(status_code=502, detail="外部大模型服务网关异常。")
            
        result_json = response.json()
        raw_answer = result_json["choices"][0]["message"]["content"].strip()
        source_text = ""
        if "参考信息中未提及" not in raw_answer:
            if context_list and context != "未能在知识库中找到相关背景知识。":
                source_text = "\n\n参考来源：\n"
                for i, c in enumerate(context_list):
                    snippet = c[:100].replace('\n', ' ') + "..." if len(c) > 100 else c.replace('\n', ' ')
                    source_text += f"[{i+1}] {snippet}\n"
        return {"answer": raw_answer + source_text}

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
        
        # if is_duplicate:
        #     return {
        #         "status": "success", 
        #         "message": f"知识库中已存在内容完全相同的文件，触发极速秒传，无需重复消耗 GPU 算力！"
        #     }
        if is_duplicate:
            raise HTTPException(
                status_code=409, 
                detail=f"系统级防卫拦截：经数字指纹比对，当前隔离域 ({project_name}) 已存在同源文件 (MD5: {file_md5})，拒绝重复入库请求以防止向量污染。"
            )

        # --- 4. 正常保存文件到本地 ---
        project_dir = get_kb_path(project_name)
        os.makedirs(project_dir, exist_ok=True)
        file_path = os.path.join(project_dir, file.filename)
        
        with open(file_path, "wb") as f:
            f.write(file_content) # 直接使用刚才读取在内存里的 file_content
            
        # --- 5. 解析文件并切片 ---
        chunks = await loop.run_in_executor(None, process_document, file_path)
        
        if chunks is None or not chunks.get("text"):
            raise HTTPException(status_code=400, detail="文件解析失败、格式不支持或内容为空。")
            
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






