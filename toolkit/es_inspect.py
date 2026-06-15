#!/usr/bin/env python3
"""
简单的 Elasticsearch 可视化查看脚本：
- 列出当前所有索引及文档数
- 预览指定索引中的前 N 条文档（包含部分字段）

用法示例：
    python inspect_es.py                  # 默认连接 http://localhost:9200，列出索引
    python inspect_es.py --index index    # 预览名为 index 的索引前 5 条数据
    python inspect_es.py --index kb_vector --size 10
"""

from __future__ import annotations

import argparse
from pprint import pprint

from elasticsearch import Elasticsearch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect Elasticsearch indices and sample documents.")
    parser.add_argument(
        "--host",
        default="http://localhost:9200",
        help="Elasticsearch 地址（默认：http://localhost:9200）",
    )
    parser.add_argument(
        "--index",
        default=None,
        help="要预览的索引名称；不指定则只列出所有索引和文档数。",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=5,
        help="预览文档条数（默认 5）",
    )
    return parser.parse_args()


def list_indices(es: Elasticsearch) -> None:
    print("=== 当前索引列表 ===")
    stats = es.indices.stats()["indices"]
    for name, info in stats.items():
        count = info["total"]["docs"]["count"]
        print(f"- {name}: {count} docs")
    print()


def preview_index(es: Elasticsearch, index: str, size: int) -> None:
    print(f"=== 预览索引: {index} （前 {size} 条）===\n")
    if not es.indices.exists(index=index):
        print(f"索引不存在：{index}")
        return

    resp = es.search(
        index=index,
        body={"query": {"match_all": {}}, "size": size},
    )
    hits = resp.get("hits", {}).get("hits", [])
    if not hits:
        print("（没有文档）")
        return

    for i, hit in enumerate(hits, 1):
        print(f"--- 文档 {i} ---")
        # 只展示 _id 和 _source，方便查看
        doc = {
            "_id": hit.get("_id"),
            "_score": hit.get("_score"),
            "_source": hit.get("_source"),
        }
        pprint(doc, width=120)
        print()


def main() -> None:
    args = parse_args()
    es = Elasticsearch(args.host)

    if not es.ping():
        print(f"无法连接到 Elasticsearch: {args.host}")
        return

    list_indices(es)

    if args.index:
        preview_index(es, args.index, args.size)


if __name__ == "__main__":
    main()


