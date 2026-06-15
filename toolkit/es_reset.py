#!/usr/bin/env python3
"""
清空 / 重建 Elasticsearch 索引的小工具。

功能：
- 删除脚本中指定的 "写死" 的索引（如果存在）
- 可选：删除后立即重新创建空索引（仅结构，不包含任何文档）

用法示例：
    # 删除脚本中指定的索引
    python reset_es_index.py

    # 删除并按当前项目的向量索引结构重建
    python reset_es_index.py --recreate
"""

from __future__ import annotations

import argparse
from elasticsearch import Elasticsearch

# ================= 配置区域 =================
# 在这里填写你要操作的固定索引名称
TARGET_INDEX_NAME = "index_user_test"  
# ===========================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delete (and optionally recreate) a hardcoded Elasticsearch index.")
    parser.add_argument(
        "--host",
        default="http://localhost:9200",
        help="Elasticsearch 地址（默认：http://localhost:9200）",
    )
    # 注意：--index 参数已被移除，改为使用全局变量 TARGET_INDEX_NAME
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="删除后按照当前向量检索的 mapping 重新创建空索引",
    )
    return parser.parse_args()


def recreate_index(es: Elasticsearch, index_name: str) -> None:
    """
    使用与 VectorRetriever.build_index 中相同的 mapping / settings 重建索引。
    """
    properties = {
        "filename": {"type": "text"},
        "content": {"type": "text", "analyzer": "custom_analyzer"},
        "embedding": {
            "type": "dense_vector",
            "dims": 1024,
            "index": True,
            "similarity": "cosine",
        },
        "date": {"type": "date"},
    }

    index_config = {
        "settings": {
            "analysis": {
                "tokenizer": {
                    "standard_tokenizer": {
                        "type": "standard",
                    }
                },
                "filter": {
                    "custom_stop_filter": {
                        "type": "stop",
                        "stopwords_path": "stopwords.txt",
                    }
                },
                "analyzer": {
                    "custom_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard_tokenizer",
                        "filter": [
                            "lowercase",
                            "custom_stop_filter",
                        ],
                    }
                },
            }
        },
        "mappings": {
            "properties": properties,
        },
    }

    # 兼容性处理：尝试使用 body 参数（旧版），如果失败则解包参数（新版 8.x+）
    try:
        es.indices.create(index=index_name, body=index_config)
    except TypeError:
        es.indices.create(index=index_name, **index_config)
        
    print(f"已重新创建空索引：{index_name}")


def main() -> None:
    args = parse_args()
    es = Elasticsearch(args.host)

    # 这里直接使用写死的变量
    index_name = TARGET_INDEX_NAME

    if not es.ping():
        print(f"无法连接到 Elasticsearch: {args.host}")
        return

    print(f"准备操作的目标索引是: 【 {index_name} 】")

    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
        print(f"已删除索引：{index_name}")
    else:
        print(f"索引不存在，无需删除：{index_name}")

    if args.recreate:
        recreate_index(es, index_name)


if __name__ == "__main__":
    main()