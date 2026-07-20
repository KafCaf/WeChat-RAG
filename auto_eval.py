import json
import os
import time
import requests
import re
import csv
from collections import defaultdict

# ================= 核心配置区 =================
RAG_API_URL = os.getenv("RAG_API_URL", "http://127.0.0.1:6006/chat")
JUDGE_API_KEY = os.getenv("JUDGE_API_KEY", "")
JUDGE_API_URL = os.getenv("JUDGE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
# ==============================================

def load_test_cases(file_path):
    print(f"正在加载测试集: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        cases = json.load(f)
    print(f"成功加载 {len(cases)} 条测试用例。\n")
    return cases

def query_rag_system(question, project_name=None):
    payload = {
        "message": question,
        "project_name": project_name,
        "history": [],
        "top_k": 6
    }
    start_time = time.time()
    try:
        response = requests.post(RAG_API_URL, json=payload, timeout=60)
        response.raise_for_status()
        res_json = response.json()
        
        answer = res_json.get("answer", "")
        context = res_json.get("context", str(res_json)) 
        latency = time.time() - start_time
        return answer, context, latency
    except Exception as e:
        print(f"RAG 请求失败: {e}")
        return "请求失败", "", 0.0

def evaluate_with_llm_judge(question, ground_truth, context, answer):
    prompt = f"""你是一个严谨的 RAG 问答系统评估专家。请你根据提供的信息，对系统的表现进行打分。

请严格按照以下维度打分并只输出 JSON 格式：
1. "Hit_Rate" (数字 1 或 5): [召回上下文] 是否包含了回答所需信息？包含给5，无关给1。
2. "Faithfulness" (数字 1-5): [系统回答] 是否完全基于 [召回上下文] 且没有幻觉？1分严重幻觉，5分绝对忠实。
3. "Relevance" (数字 1-5): [系统回答] 是否完美解答了 [用户问题] 且与 [黄金答案] 核心一致？1分答非所问，5分完美解答。

============= 数据输入 =============
[用户问题]: {question}
[黄金答案]: {ground_truth}
[召回上下文]: {context}
[系统回答]: {answer}
"""
    headers = {
        "Authorization": f"Bearer {JUDGE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "qwen3.5-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1 
    }
    
    try:
        response = requests.post(JUDGE_API_URL, headers=headers, json=payload, timeout=30)
        content = response.json()['choices'][0]['message']['content']
        
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            scores = json.loads(json_match.group(0))
            return scores
        else:
            return {"Hit_Rate": 0, "Faithfulness": 0, "Relevance": 0}
    except Exception as e:
        print(f"裁判大模型请求失败: {e}")
        return {"Hit_Rate": 0, "Faithfulness": 0, "Relevance": 0}

def main():
    test_cases = load_test_cases('/root/chat/test-cases.json')
    
    stats = defaultdict(lambda: {"count": 0, "latency": 0.0, "hit_rate": 0, "faithfulness": 0.0, "relevance": 0.0})
    detailed_results = [] # 用于保存每一题详细数据的列表

    for i, case in enumerate(test_cases):
        question, ground_truth, category = case[0], case[1], case[2]
        project_name = case[3] if len(case) >= 4 else None
        print(f"[{i+1}/{len(test_cases)}] 正在测试 ({category}): {question[:30]}...")
        
        answer, context, latency = query_rag_system(question, project_name)
        
        if category.startswith("反例"):
            if "未提及" in answer or "不知道" in answer:
                scores = {"Hit_Rate": 5, "Faithfulness": 5, "Relevance": 5}
            else:
                scores = {"Hit_Rate": 1, "Faithfulness": 1, "Relevance": 1}
        else:
            scores = evaluate_with_llm_judge(question, ground_truth, context, answer)
        
        # 记录分类汇总数据
        stats[category]["count"] += 1
        stats[category]["latency"] += latency
        stats[category]["hit_rate"] += 1 if scores.get("Hit_Rate", 0) >= 4 else 0 
        stats[category]["faithfulness"] += scores.get("Faithfulness", 0)
        stats[category]["relevance"] += scores.get("Relevance", 0)
        
        # 记录每道题的详细明细
        detailed_results.append({
            "维度": category,
            "测试问题": question,
            "端到端耗时(s)": round(latency, 2),
            "召回得分": scores.get("Hit_Rate", 0),
            "忠实度得分": scores.get("Faithfulness", 0),
            "相关性得分": scores.get("Relevance", 0),
            "系统实际回答": answer.replace('\n', ' ') # 消除换行符，防CSV错乱
        })
        
        time.sleep(1)

    # ================= 打印并导出数据 =================
    print("\n" + "="*60)
    print("自动化定量评估汇总报告")
    print("="*60)
    
    total_count, total_lat, total_hit, total_faith, total_rel = 0, 0, 0, 0, 0
    summary_rows = []
    
    for cat, data in stats.items():
        count = data["count"]
        avg_lat = data["latency"] / count
        hit_rate = (data["hit_rate"] / count) * 100
        avg_faith = data["faithfulness"] / count
        avg_rel = data["relevance"] / count
        
        total_count += count
        total_lat += data["latency"]
        total_hit += data["hit_rate"]
        total_faith += data["faithfulness"]
        total_rel += data["relevance"]
        
        row_str = f"{cat:<15} | {count:<5} | {hit_rate:>9.1f}%   | {avg_faith:>8.2f}   | {avg_rel:>8.2f}   | {avg_lat:>8.2f}s"
        print(row_str)
        summary_rows.append(f"| {cat} | {count} | {hit_rate:.1f}% | {avg_faith:.2f} | {avg_rel:.2f} | {avg_lat:.2f}s |")
        
    print("-" * 75)
    final_hit_rate = (total_hit/total_count)*100
    final_faith = total_faith/total_count
    final_rel = total_rel/total_count
    final_lat = total_lat/total_count
    
    final_row = f"{'总体加权平均':<15} | {total_count:<5} | {final_hit_rate:>9.1f}%   | {final_faith:>8.2f}   | {final_rel:>8.2f}   | {final_lat:>8.2f}s"
    print(final_row)
    print("="*60)

    # --- 💥 核心修改：将数据输出到文件 ---
    
    # 1. 导出详细明细为 CSV (可用 Excel 打开)
    csv_file = 'rag_evaluation_details.csv'
    with open(csv_file, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["维度", "测试问题", "端到端耗时(s)", "召回得分", "忠实度得分", "相关性得分", "系统实际回答"])
        writer.writeheader()
        writer.writerows(detailed_results)

    # 2. 导出汇总报告为 Markdown
    md_file = 'rag_evaluation_summary.md'
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write("### 自动化定量评估汇总报告\n\n")
        f.write("| 测试用例维度 | 数量 | Top-5 召回率 | 答案忠实度 | 意图响应率 | 平均耗时 (s) |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")
        f.write("\n".join(summary_rows) + "\n")
        f.write(f"| **总体加权平均** | **{total_count}** | **{final_hit_rate:.1f}%** | **{final_faith:.2f}** | **{final_rel:.2f}** | **{final_lat:.2f}s** |\n")

    print(f"\n[文件导出成功] 📊 详细测试数据已保存至: {csv_file}")
    print(f"[文件导出成功] 📝 论文汇总表格已保存至: {md_file}")

if __name__ == "__main__":
    main()