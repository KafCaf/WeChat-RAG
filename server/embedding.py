from configs.model_configs import MODEL_PATH, EMBED_CONFIG, SPLITTER_CONFIG
from utils import detect_device
from typing import Literal, List, Dict, Any


def embedding_device(device: str = None) -> Literal["cuda", "mps", "cpu"]:
    device = device or EMBED_CONFIG["embed_device"]
    if device not in ["cuda", "mps", "cpu"]:
        device = detect_device()
    return device


def load_embeddings(model, device) -> Any:
    if model == "text-embedding-ada-002":
        from langchain.embeddings.openai import OpenAIEmbeddings
        embeddings = OpenAIEmbeddings(model=model,
                                      openai_api_key=MODEL_PATH["embed_model"][model],
                                      chunk_size=SPLITTER_CONFIG["chunk_size"])
    elif model == "bge-m3":
        from FlagEmbedding import BGEM3FlagModel
        embeddings = BGEM3FlagModel(MODEL_PATH["embed_model"][model],
                                    use_fp16=True,
                                    use_multiprocessing=False,
                                    devices="cuda:0")
    elif 'bge-' in model:
        from langchain.embeddings import HuggingFaceBgeEmbeddings
        if 'zh' in model:  #zh:中文版本
            # for chinese model
            query_instruction = "为这个句子生成表示以用于检索相关文章："
        elif 'en' in model:  #en:英文版本
            # for english model
            query_instruction = "Represent this sentence for searching relevant passages:"
        else:
            # maybe ReRanker or else, just use empty string instead
            query_instruction = ""
        embeddings = HuggingFaceBgeEmbeddings(model_name=MODEL_PATH["embed_model"][model],
                                            model_kwargs={'device': "cuda:0"},
                                            query_instruction=query_instruction)
        if model == "bge-large-zh-noinstruct":  # bge large -noinstruct embedding
            embeddings.query_instruction = ""
    else:
        from langchain.embeddings.huggingface import HuggingFaceEmbeddings
        embeddings = HuggingFaceEmbeddings(model_name=r"/home/xdn/RAG/RAGProject/Embedding_models/gte_large_en_v1_5",
                                        model_kwargs={'trust_remote_code': True, 'device': 'cuda'},
                                        encode_kwargs={'normalize_embeddings': True})
    
    return embeddings

def embed_texts(
        texts: List[str],
        embed_model: str = EMBED_CONFIG["embed_model"],
        to_query: bool = False,
):
    '''
    data=List[List[float]]
    '''
    embeddings = load_embeddings(model=embed_model, device=embedding_device())
    data = embeddings.embed_documents(texts)
    return data


def embed_documents(docs, embed_model) -> Dict:
    
    output = embed_model.encode(docs, return_dense=True, return_sparse=False, return_colbert_vecs=False)
    embeddings = output['dense_vecs']
    
    if embeddings is not None:
        return {
            "texts": docs,
            "embeddings": embeddings,
        }


# ==================== 云端 Embedding API (百炼 text-embedding-v4) ====================

import os
import httpx
import numpy as np


async def cloud_embed_documents(docs: List[str], api_key: str = None, model: str = None) -> Dict:
    """
    通过阿里云百炼云端 API 生成 embedding，替代本地 BGE-M3。
    返回格式兼容 embed_documents：{"texts": [...], "embeddings": np.array([...])}
    """
    api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
    model = model or os.getenv("DASHSCOPE_EMBED_MODEL", "text-embedding-v4")
    url = os.getenv("DASHSCOPE_EMBED_URL",
                    "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "input": {"texts": docs},
        "parameters": {"text_type": "document"}
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    embeddings_list = data["output"]["embeddings"]
    # 按 text_index 排序确保顺序一致
    embeddings_list.sort(key=lambda x: x["text_index"])
    embeddings = np.array([e["embedding"] for e in embeddings_list], dtype=np.float32)

    return {
        "texts": docs,
        "embeddings": embeddings,
    }


def cloud_embed_documents_sync(docs: List[str], api_key: str = None, model: str = None) -> Dict:
    """同步版本，用于 run_in_executor"""
    import requests

    api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
    model = model or os.getenv("DASHSCOPE_EMBED_MODEL", "text-embedding-v4")
    url = os.getenv("DASHSCOPE_EMBED_URL",
                    "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "input": {"texts": docs},
        "parameters": {"text_type": "document"}
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    embeddings_list = data["output"]["embeddings"]
    embeddings_list.sort(key=lambda x: x["text_index"])
    embeddings = np.array([e["embedding"] for e in embeddings_list], dtype=np.float32)

    return {
        "texts": docs,
        "embeddings": embeddings,
    }


class CloudEmbedModel:
    """
    云端 Embedding 模型包装类，兼容 BGE-M3 的 .encode() 接口。
    仅支持 return_dense=True (不含 ColBERT/SPLARSE)。
    """
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.model = model or os.getenv("DASHSCOPE_EMBED_MODEL", "text-embedding-v4")

    def encode(self, docs, return_dense=True, return_sparse=False, return_colbert_vecs=False):
        result = cloud_embed_documents_sync(docs, api_key=self.api_key, model=self.model)
        output = {}
        if return_dense:
            output["dense_vecs"] = result["embeddings"]
        if return_sparse:
            output["lexical_weights"] = [None] * len(docs)
        if return_colbert_vecs:
            output["colbert_vecs"] = [None] * len(docs)
        return output

    def colbert_score(self, q_vecs, d_vecs):
        # 云端模型不支持 ColBERT，返回 0
        return 0.0