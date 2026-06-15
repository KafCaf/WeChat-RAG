import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from configs.model_configs import MODEL_PATH

def load_reranker(model_name="bge-reranker-large", device="cuda"):
    model_path = MODEL_PATH["reranker_model"][model_name]
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    
    model = AutoModelForSequenceClassification.from_pretrained(model_path, device_map="auto").eval()
    return model, tokenizer

def get_rerank_scores(model, tokenizer, query, docs):
    """计算查询（query）与每个文档（docs）的相关性分数"""
    pairs = [[query, doc] for doc in docs]
    
    with torch.no_grad():
        inputs = tokenizer(pairs, padding=True, truncation=True, return_tensors='pt', max_length=512).to(model.device)
        scores = model(**inputs, return_dict=True).logits.view(-1, ).float()
        return scores.tolist()


# ==================== 云端 Reranker API (百炼 gte-rerank) ====================

import os as _os
import requests as _requests


def cloud_rerank(query: str, documents: list, api_key: str = None, model: str = None, top_n: int = 5) -> list:
    """
    通过阿里云百炼云端 API 进行重排序。
    返回: [(doc_index, relevance_score), ...] 按分数降序排列
    """
    api_key = api_key or _os.getenv("DASHSCOPE_API_KEY", "")
    model = model or _os.getenv("DASHSCOPE_RERANK_MODEL", "gte-rerank")
    url = _os.getenv("DASHSCOPE_RERANK_URL",
                     "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "input": {
            "query": query,
            "documents": documents
        },
        "parameters": {
            "top_n": min(top_n, len(documents)),
            "return_documents": False
        }
    }

    resp = _requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    results = data["output"]["results"]
    return [(r["index"], r["relevance_score"]) for r in results]