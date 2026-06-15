from retrievers.base import BaseRetrieval
from elasticsearch.helpers import bulk
import numpy as np

class VectorRetrieval(BaseRetrieval):
    
    def get_documents_with_ids(self, doc_ids, index):
        if not doc_ids:
            return []
        response = self.es.mget(
            index = index,
            ids = doc_ids
        )
        return [hit["_source"]["content"] for hit in response["docs"]]
    
    def calculate_rrf(self, bm25_results, vector_results, k=10):
        all_docs = {}
        
        for doc_id, rank in bm25_results:
            all_docs[doc_id] = {"bm25_rank": rank, "vector_rank": None}
        
        for doc_id, rank in vector_results:
            if doc_id not in all_docs:
                all_docs[doc_id] = {"bm25_rank": None, "vector_rank": rank}
            else:
                all_docs[doc_id]["vector_rank"] = rank
        
        for doc_id, ranks in all_docs.items():
            bm25_rank = ranks["bm25_rank"] if ranks["bm25_rank"] is not None else float("inf")
            vector_rank = ranks["vector_rank"] if ranks["vector_rank"] is not None else float("inf")
            
            rrf_score = (1 / (k + bm25_rank)) + (1 / (k + vector_rank))
            all_docs[doc_id]["rrf_score"] = rrf_score

        sorted_docs = sorted(all_docs.items(), key=lambda x: x[1]["rrf_score"], reverse=True)

        return sorted_docs

    def bm25_retrieve(self, query, index, size=1000, project_name=None):
        query_body = {
            "query": {
                "bool": {
                    "must": [{"match": {"content": query}}]
                }
            },
            "size": size
        }
        # 🌟 如果传入了项目名，强制过滤
        if project_name:
            query_body["query"]["bool"]["filter"] = [{"term": {"project_name": project_name}}]
            
        try:
            response = self.es.search(index=index, body=query_body)
        except TypeError:
            response = self.es.search(index=index, **query_body)
        return response
    
    def vector_retrieve(self, query, index, size=1000, project_name=None):
        query_embedding = self._docs_to_embeddings([query])
        
        # 构建基础的 bool 查询
        base_query = {"match_all": {}}
        if project_name:
            base_query = {
                "bool": {
                    "filter": [{"term": {"project_name": project_name}}]
                }
            }

        query_body = {
            "query": {
                "script_score": {
                    "query": base_query, # 🌟 替换为带有 filter 的查询
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                        "params": {
                            "query_vector": query_embedding["embeddings"][0]
                        }
                    }
                }
            },
            "size": size
        }
        try:
            response = self.es.search(index=index, body=query_body)
        except TypeError:
            response = self.es.search(index=index, **query_body)
        return response

    def build_index(self, index_name, chunks):
        if not self.es.indices.exists(index=index_name):
            properties = {
                "filename": {"type": "text"},
                "project_name": {"type": "keyword"},
                "file_hash": {"type": "keyword"},
                "content": {"type": "text", "analyzer": "custom_analyzer"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": 1024,
                    "index": True,
                    "similarity": "cosine"
                },
                "date": {"type": "date"}
            }

            # 兼容新旧版本的 Elasticsearch 客户端
            index_config = {
                "settings": {
                    "analysis": {
                        "tokenizer": {
                            "standard_tokenizer": {
                                "type": "standard"
                            }
                        },
                        "filter": {
                            "custom_stop_filter": {
                                "type": "stop",
                                "stopwords_path": "stopwords.txt"
                            },
                        },
                        "analyzer": {
                            "custom_analyzer": {
                                "type": "custom",
                                "tokenizer": "standard_tokenizer",
                                "filter": [
                                    "lowercase",
                                    "custom_stop_filter",
                                    ]
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": properties
                }
            }
            
            try:
                self.es.indices.create(index=index_name, body=index_config)
            except TypeError:
                # 新版本客户端不支持 body 参数，直接传递配置
                self.es.indices.create(index=index_name, **index_config)
        
        embeddings = self._docs_to_embeddings(chunks["text"])
        actions = [
            {
                "_index": index_name,
                "_source": {
                    "filename": chunks["filename"],
                    "project_name": chunks.get("project_name", "default"),
                    "file_hash": chunks.get("file_hash", "unknown"),
                    "content": chunk,
                    "embedding": embedding,
                    "date": chunks['date']
                }
            }
            for chunk, embedding in zip(chunks["text"], embeddings["embeddings"])
        ]
        bulk(self.es, actions)
        self.es.indices.refresh(index=index_name)
        
    def search_rrf(self, index_name, query, top_k1=1000, top_k2=5, project_name=None, **kwargs):
        # 🌟 透传 project_name 给底层的召回函数
        response = self.bm25_retrieve(query, index_name, top_k1, project_name)
        bm25_ranks = [(hit["_id"], idx + 1) for idx, hit in enumerate(response["hits"]["hits"])]
        
        response = self.vector_retrieve(query, index_name, top_k1, project_name)
        vector_ranks = [(hit["_id"], idx + 1) for idx, hit in enumerate(response["hits"]["hits"])]

        final_sorted_docs = self.calculate_rrf(bm25_ranks, vector_ranks)
        # 🌟 扩大候选池：取前 20 个进精排（原来是 4 个）
        sorted_doc_ids = [doc_id for doc_id, result in final_sorted_docs][:20]
        docs = self.get_documents_with_ids(sorted_doc_ids, index_name)
        
        # 🌟 使用云端 Reranker 替代 ColBERT 精排
        try:
            from server.reranker import cloud_rerank
            rerank_results = cloud_rerank(query, docs, top_n=top_k2)
            sorted_docs = [docs[idx] for idx, _ in rerank_results]
            sorted_scores = [score for _, score in rerank_results]
        except Exception:
            # 降级：使用 ColBERT（云端模型可能返回 0）
            output_1 = self.embed_model.encode([query], return_dense=False, return_sparse=False, return_colbert_vecs=True)
            output_2 = self.embed_model.encode(docs, return_dense=False, return_sparse=False, return_colbert_vecs=True)
            
            colbert_scores = []
            for i in range(len(docs)):
                colbert_score = float(self.embed_model.colbert_score(output_1['colbert_vecs'][0], output_2['colbert_vecs'][i]))
                colbert_scores.append(colbert_score)
            zipped = list(zip(docs, colbert_scores))
            sorted_zipped = sorted(zipped, key=lambda x: x[1], reverse=True)
            sorted_docs = [doc for doc, _ in sorted_zipped][:top_k2]
            sorted_scores = [score for _, score in sorted_zipped][:top_k2]
        
        return sorted_docs, sorted_scores

    def search(self, index_name, query, top_k1=1000, top_k2=5, **kwargs):
        """
        实现 BaseRetrieval 抽象的统一搜索接口。
        默认使用 RRF + ColBERT 精排的检索流程，并返回 (docs, scores)。
        """
        return self.search_rrf(index_name=index_name, query=query, top_k1=top_k1, top_k2=top_k2, **kwargs)
    
    def check_hash_exists(self, index_name, file_hash, project_name):
        """检查 ES 中是否已经存在相同内容（哈希值）的文件"""
        if not self.es.indices.exists(index=index_name):
            return False
            
        query_body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"project_name": project_name}},
                        {"term": {"file_hash": file_hash}} # 精确匹配哈希值
                    ]
                }
            }
        }
        try:
            # size=0 表示我们只关心数量，不返回具体切片内容，速度极快
            response = self.es.search(index=index_name, body=query_body, size=0)
            return response['hits']['total']['value'] > 0
        except Exception as e:
            print(f"哈希查重异常: {e}")
            return False
        
    def delete_file_chunks(self, index_name, filename, project_name):
        """根据文件名和项目名删除 Elasticsearch 中的旧切片，实现覆盖式更新"""
        if not self.es.indices.exists(index=index_name):
            return
            
        query_body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"project_name": project_name}},
                        {"match_phrase": {"filename": filename}}
                    ]
                }
            }
        }
        try:
            response = self.es.delete_by_query(index=index_name, body=query_body, ignore=[400, 404])
            self.es.indices.refresh(index=index_name)
            deleted_count = response.get("deleted", 0)
            if deleted_count > 0:
                print(f"[数据清理] 已清理项目【{project_name}】中文件【{filename}】的 {deleted_count} 个旧切片。")
        except Exception as e:
            print(f"[数据清理] 清理旧数据时出错: {e}")