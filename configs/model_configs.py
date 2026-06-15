EMBED_CONFIG = {
    "embed_model": "bge-m3",
    # "embed_model": "gte-large-en-v1.5",

    "embed_device": "cuda",
}

SPLITTER_CONFIG = {
    "chunk_size":256,
}

LLM_CONFIG = {
    "llm_model": "qwen2.5-3B-instruct",  
    "llm_device": "cuda",
}

RERANKER_CONFIG = {
    "reranker_model": "bge-reranker-large",
    "reranker_device": "cuda",
}

MODEL_PATH = {
    "embed_model": {
        "bge-large-en": "",
        #"bge-m3": "/home/user_test/bishe_project/chat-v1/models/bge-m3", # 注意：如果你换了向量模型，这里的路径也要改成 /root/autodl-tmp/models/...
        "bge-m3": "/root/autodl-tmp/models/BAAI/bge-m3",
    },
    "llm_model": {
        "llama3-8B-instruct": "/home/user_test/bishe_project/chat-v1/models/Llama-3-8B-Instruct",
        "qwen2.5-7B-instruct": "/home/user_test/bishe_project/chat-v1/models/Qwen2.5-7B-Instruct",
        "qwen2.5-3B-instruct": "/root/autodl-tmp/models/Qwen2.5-3B-Instruct",
        "LLama-3-8B-Tele-it": ""
    },
    "reranker_model": {
        "bge-reranker-large": ""
    }
}