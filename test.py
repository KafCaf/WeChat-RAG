import os
import sys
import requests
import time
import json
import readline

# ================= 底层环境防御配置 =================
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stdin.encoding.lower() != 'utf-8':
    sys.stdin.reconfigure(encoding='utf-8')
# ===================================================

API_URL = "http://127.0.0.1:6006/chat"

def interactive_chat_test():
    """
    终端交互式测试入口 (已加入速度监控)
    """
    print("=" * 50)
    print("[系统] RAG API 对话测试终端已启动")
    print("[提示] 输入 'quit' 或 'exit' 退出测试")
    print("[提示] 输入 'clear' 清空当前的对话历史")
    print("[提示] 输入 'batch' 进入自动化批量幻觉测试")
    print("=" * 50)

    chat_history = []
    target_project = None#"国际杰青计划"

    with requests.Session() as session:
        while True:
            try:
                user_input = input("\n[用户] 请输入您的问题: ").strip()
                
                if user_input.lower() in ['quit', 'exit']:
                    print("[系统] 退出测试终端。")
                    break
                    
                if user_input.lower() == 'clear':
                    chat_history.clear()
                    print("[系统] 历史记录已清空，上下文重置完成。")
                    continue
                    
                if user_input.lower() == 'batch':
                    run_batch_hallucination_test(session)
                    continue
                    
                if not user_input:
                    continue

                payload = {
                    "message": user_input,
                    "project_name": target_project,
                    "history": chat_history,
                    "top_k": 10
                }

                print("[系统] 正在调度 RAG 检索引擎与 LLM，请稍候...")
                
                # 开始计时 (客户端感知端到端延迟)
                start_time = time.time()
                
                response = session.post(API_URL, json=payload, timeout=60)
                response.raise_for_status()
                
                result = response.json()
                
                # 结束计时
                end_time = time.time()
                latency = end_time - start_time
                
                answer = result.get("answer", "系统异常：未获取到有效载荷")
                
                print(f"\n[助手] (耗时: {latency:.2f}秒)\n{answer}")
                print("-" * 50)
                
                chat_history.append([user_input, answer])
                
            except requests.exceptions.Timeout:
                print("\n[错误] API 请求超时 (Timeout)。服务端负载过高或路由不可达。")
            except requests.exceptions.RequestException as e:
                print(f"\n[错误] 网络 IO 异常: {e}")
                if response is not None:
                    print(f"[上下文] HTTP 状态码: {response.status_code}")
            except KeyboardInterrupt:
                print("\n[系统] 捕获 SIGINT 中断信号，安全退出进程。")
                break

def run_batch_hallucination_test(session):
    """
    自动化批量幻觉测试引擎
    设计意图: 自动运行预设的测试用例，验证大模型的召回率与防幻觉（拒答）能力。
    """
    print("\n" + "=" * 50)
    print("开始运行【幻觉与准确度自动化测试集】")
    print("=" * 50)
    
    # 构建测试集：正例（应该回答得出）和反例（必须拒答，防止幻觉）
    test_cases = [
        # --- 忠实度测试：文档中存在的明确事实 ---
        {"type": "正例-细节提取", "question": "国际杰青计划管理办法中，如果外籍专家接受工作同意书后因故不能来华，应该怎么办？"},
        {"type": "正例-条件判断", "question": "申报发展中国家技术培训班的单位，需要满足什么注册条件？"},
        
        # --- 幻觉防御测试：常识性诱导（背景知识中没有） ---
        {"type": "反例-日常闲聊", "question": "你好，请问今天北京天气怎么样？"},
        {"type": "反例-无关知识", "question": "请告诉我红烧肉的做法。"},
        {"type": "反例-编造政策", "question": "《国际宇宙探索管理办法》中规定去火星的补贴是多少？"},
    ]
    
    report = []
    
    for idx, case in enumerate(test_cases, 1):
        print(f"\n测试用例 [{idx}/{len(test_cases)}] - {case['type']}")
        print(f"Q: {case['question']}")
        
        payload = {
            "message": case["question"],
            "project_name": None, # 全局检索
            "history": [],        # 每次测试保持独立上下文
            "top_k": 6
        }
        
        start_time = time.time()
        try:
            response = session.post(API_URL, json=payload, timeout=60)
            response.raise_for_status()
            answer = response.json().get("answer", "")
            latency = time.time() - start_time
            
            print(f"A: {answer}")
            print(f"[耗时: {latency:.2f}s]")
            
            report.append({
                "case": case["question"],
                "type": case["type"],
                "latency": latency,
                "status": "Success"
            })
            
        except Exception as e:
            print(f"测试失败: {str(e)}")
            report.append({
                "case": case["question"],
                "type": case["type"],
                "latency": 0,
                "status": f"Error: {str(e)}"
            })
            
        # 适度休眠，避免触发 API 并发限流
        time.sleep(1)
        
    # 打印测试统计
    successful_cases = [r for r in report if r["status"] == "Success"]
    avg_latency = sum(r["latency"] for r in successful_cases) / len(successful_cases) if successful_cases else 0
    
    print("\n" + "=" * 50)
    print("幻觉与性能批量测试报告")
    print(f"完成用例: {len(successful_cases)}/{len(test_cases)}")
    print(f"平均端到端延迟: {avg_latency:.2f} 秒")
    print("人工校验指标：")
    print("1. 正例是否精准带出了【参考来源】的索引？")
    print("2. 反例（红烧肉/天气）是否严格回复了“参考信息中未提及”？")
    print("=" * 50)


if __name__ == '__main__':
    interactive_chat_test()