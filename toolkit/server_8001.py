"""
模型服务端 - 基于 AsyncLLMEngine 的高并发版本
启动命令: python server_8001.py
"""
import os
import sys

# ================= 配置区域 =================
GPU_MEMORY_UTILIZATION = 0.7 
MAX_MODEL_LEN = 8192 
# ===========================================

os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import uvicorn
import uuid
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager

from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.engine.async_llm_engine import AsyncLLMEngine
from vllm.sampling_params import SamplingParams
from vllm.utils import random_uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vLLM-Server")

engine = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    
    model_path = "/root/autodl-tmp/models/Qwen2.5-3B-Instruct"
    
    try:
        logger.info("=" * 80)
        logger.info(f"🚀 正在初始化 AsyncLLMEngine (单卡高并发模式)...")
        logger.info(f"📍 模型路径: {model_path}")
        logger.info(f"💾 显存限制: {GPU_MEMORY_UTILIZATION*100}%")
        logger.info("=" * 80)

        engine_args = AsyncEngineArgs(
            model=model_path,
            # ✅ 修复点3：删除了 tensor_parallel_size=2，因为你是单卡
            max_model_len=MAX_MODEL_LEN,
            gpu_memory_utilization=GPU_MEMORY_UTILIZATION,
            trust_remote_code=True,
            dtype="auto", # ✅ 修复点4：改为 auto，让框架自己适配最稳妥的精度
            enforce_eager=True, 
            disable_log_requests=True
        )
        
        engine = AsyncLLMEngine.from_engine_args(engine_args)
        
        logger.info("=" * 80)
        logger.info("✅ 3B 模型加载完成！高并发服务已就绪")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ 模型加载失败: {str(e)}", exc_info=True)
        raise
    
    yield
    logger.info("🔄 服务正在关闭...")

app = FastAPI(title="vLLM Async Server", lifespan=lifespan)

class GenerateRequest(BaseModel):
    prompt: str
    temperature: float = 0.6
    top_p: float = 0.95
    max_tokens: int = 4096 
    repetition_penalty: float = 1.1

class GenerateResponse(BaseModel):
    text: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: Optional[str] = None

class ChatTemplateRequest(BaseModel):
    messages: list
    tokenize: bool = False
    add_generation_prompt: bool = True

@app.get("/health")
async def health_check():
    if engine is None:
        raise HTTPException(status_code=503, detail="Model not initialized")
    return {"status": "healthy", "mode": "async_engine"}

@app.post("/generate", response_model=GenerateResponse)
async def generate_text(request: GenerateRequest):
    if engine is None:
        raise HTTPException(status_code=503, detail="Model not initialized")
    
    request_id = random_uuid()
    
    sampling_params = SamplingParams(
        temperature=request.temperature,
        top_p=request.top_p,
        max_tokens=request.max_tokens,
        repetition_penalty=request.repetition_penalty,
        skip_special_tokens=True
    )
    
    try:
        results_generator = engine.generate(request.prompt, sampling_params, request_id)
        
        final_output = None
        async for request_output in results_generator:
            final_output = request_output
            
        if final_output:
            prompt_tokens = len(final_output.prompt_token_ids)
            completion_tokens = len(final_output.outputs[0].token_ids)
            text_output = final_output.outputs[0].text
            finish_reason = final_output.outputs[0].finish_reason
            
            if "</think>" in text_output:
                text_output = text_output.split("</think>")[1].strip()

            return GenerateResponse(
                text=text_output,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                finish_reason=finish_reason
            )
        else:
            raise HTTPException(status_code=500, detail="生成结果为空")
            
    except Exception as e:
        logger.error(f"生成请求失败: {str(e)}")
        if engine:
            await engine.abort(request_id)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/apply_chat_template")
async def apply_chat_template(request: ChatTemplateRequest):
    if engine is None:
        raise HTTPException(status_code=503, detail="Model not initialized")
    try:
        tokenizer = await engine.get_tokenizer()
        prompt = tokenizer.apply_chat_template(
            request.messages,
            tokenize=request.tokenize,
            add_generation_prompt=request.add_generation_prompt
        )
        return {"prompt": prompt}
    except Exception as e:
        logger.error(f"模板应用失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")