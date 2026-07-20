#!/usr/bin/env python3
"""
RAG 问答系统自动化评估脚本 (v2)
- 调用 /chat API 获取系统回答
- LLM Judge（qwen3.5-flash）对正例打分
- 反例自动判断（检查"未提及"）
- 输出 Markdown + CSV 报告
"""

import json, os, time, csv
import requests
from collections import defaultdict

# ================= 配置 =================
RAG_URL  = os.getenv("RAG_URL",  "http://127.0.0.1:6006/chat")
JUDGE_KEY = os.getenv("JUDGE_API_KEY", "") or os.getenv("DASHSCOPE_API_KEY", "")
JUDGE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
TEST_FILE = os.getenv("TEST_FILE", "test-cases.json")
OUT_DIR   = os.getenv("OUT_DIR",  ".")
# =========================================

def query_rag(question, project):
    """调用 RAG 系统，返回 answer 和上下文"""
    try:
        resp = requests.post(RAG_URL, json={
            "message": question,
            "project_name": project,
            "history": [],
            "top_k": 5
        }, timeout=60)
        data = resp.json()
        return data.get("answer", ""), data.get("context", str(data))
    except Exception as e:
        return f"[请求失败: {e}]", ""

def llm_judge(question, ground_truth, context, answer):
    """LLM 打分：召回率(1/5) + 忠实度(1-5) + 相关性(1-5)"""
    prompt = f"""你是 RAG 评估专家。请严格按以下维度打分，只输出 JSON：

1. "Hit_Rate" (1 或 5): 召回上下文是否包含回答所需信息？包含=5，无关=1
2. "Faithfulness" (1-5): 系统回答是否完全基于召回上下文、无幻觉？
3. "Relevance" (1-5): 系统回答是否完美解答用户问题、且与黄金答案核心一致？

============= 数据 =============
[用户问题]: {question}
[黄金答案]: {ground_truth}
[召回上下文]: {context[:2000]}
[系统回答]: {answer[:1000]}
"""
    try:
        resp = requests.post(JUDGE_URL, headers={
            "Authorization": f"Bearer {JUDGE_KEY}",
            "Content-Type": "application/json"
        }, json={
            "model": "qwen3.5-flash",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }, timeout=30)
        content = resp.json()["choices"][0]["message"]["content"]
        import re
        m = re.search(r'\{.*\}', content, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        print(f"  ⚠️ Judge 失败: {e}")
    return {"Hit_Rate": 0, "Faithfulness": 0, "Relevance": 0}

def main():
    # 加载测试用例 [question, ground_truth, category, project_name?]
    cases = json.load(open(TEST_FILE, encoding="utf-8"))
    print(f"📋 加载 {len(cases)} 条测试用例\n")

    stats = defaultdict(lambda: {"n": 0, "lat": 0.0, "hit": 0, "faith": 0.0, "rel": 0.0})
    rows = []

    for i, case in enumerate(cases):
        q, gt, cat = case[0], case[1], case[2]
        proj = case[3] if len(case) >= 4 else None
        print(f"[{i+1}/{len(cases)}] ({cat}) {q[:40]}...")

        t0 = time.time()
        ans, ctx = query_rag(q, proj)
        lat = time.time() - t0

        # 反例：检查是否回复"未提及"
        if cat.startswith("反例"):
            if "未提及" in ans or "不知道" in ans:
                scores = {"Hit_Rate": 5, "Faithfulness": 5, "Relevance": 5}
            else:
                scores = {"Hit_Rate": 1, "Faithfulness": 1, "Relevance": 1}
        else:
            scores = llm_judge(q, gt, ctx, ans)

        # 汇总
        stats[cat]["n"] += 1
        stats[cat]["lat"] += lat
        stats[cat]["hit"] += (1 if scores.get("Hit_Rate", 0) >= 4 else 0)
        stats[cat]["faith"] += scores.get("Faithfulness", 0)
        stats[cat]["rel"] += scores.get("Relevance", 0)

        rows.append({
            "维度": cat, "问题": q,
            "耗时(s)": round(lat, 2),
            "召回(1/5)": scores.get("Hit_Rate", 0),
            "忠实度": scores.get("Faithfulness", 0),
            "相关性": scores.get("Relevance", 0),
            "系统回答": ans.replace("\n", " ")[:200]
        })
        time.sleep(0.3)

    # ============= 输出报告 =============
    md = ["## RAG 系统自动化评估报告\n", f"**测试用例数**: {len(cases)}  |  **Judge**: qwen3.5-flash  |  **日期**: {time.strftime('%Y-%m-%d')}\n"]
    md.append("| 测试维度 | 数量 | 召回率 | 忠实度 | 相关性 | 平均耗时(s) |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")

    total_n = total_hit = 0
    total_faith = total_rel = total_lat = 0.0

    for cat, d in sorted(stats.items()):
        n = d["n"];  total_n += n
        hit = d["hit"] / n * 100;  total_hit += d["hit"]
        faith = d["faith"] / n;    total_faith += d["faith"]
        rel = d["rel"] / n;        total_rel += d["rel"]
        avg_lat = d["lat"] / n;     total_lat += d["lat"]
        md.append(f"| {cat} | {n} | {hit:.0f}% | {faith:.1f} | {rel:.1f} | {avg_lat:.1f}s |")

    total_hit = total_hit / total_n * 100
    total_faith /= total_n; total_rel /= total_n; total_lat /= total_n
    md.append(f"| **总计** | **{total_n}** | **{total_hit:.0f}%** | **{total_faith:.1f}** | **{total_rel:.1f}** | **{total_lat:.1f}s** |")

    report = "\n".join(md)
    print("\n" + report)

    # 导出 CSV
    csv_path = os.path.join(OUT_DIR, "eval_details.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["维度","问题","耗时(s)","召回(1/5)","忠实度","相关性","系统回答"])
        w.writeheader(); w.writerows(rows)
    print(f"\n📊 CSV: {csv_path}")

    # 导出 MD
    md_path = os.path.join(OUT_DIR, "eval_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"📝 报告: {md_path}")

if __name__ == "__main__":
    main()
