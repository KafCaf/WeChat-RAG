import requests
import os
import time

# ⚠️ 注意：如果你的 api.py 运行在 6006 端口，请把 5000 改为 6006
UPLOAD_URL = "http://127.0.0.1:6006/upload"
CHAT_URL = "http://127.0.0.1:6006/chat"

# 你指定的测试目标文件夹
TEST_DIR = "/root/chat/test/" 
PROJECT_NAME = "极速秒传测试项目"

def upload_single_file(file_path, attempt_desc):
    """封装的单次上传函数，记录耗时"""
    start_time = time.time()
    with open(file_path, "rb") as f:
        # 这里动态获取文件名，不再写死
        filename = os.path.basename(file_path)
        files = {"file": (filename, f)}
        data = {"project_name": PROJECT_NAME}
        
        try:
            response = requests.post(UPLOAD_URL, files=files, data=data, timeout=300)
            latency = time.time() - start_time
            
            if response.status_code == 200:
                res_data = response.json()
                status = "✅ 成功" if res_data.get("status") == "success" else "⚠️ 异常"
                msg = res_data.get("message", "无返回信息")
                print(f"   [{attempt_desc}] 耗时: {latency:.2f}秒 | {status} -> {msg}")
            else:
                print(f"   [{attempt_desc}] ❌ 失败 | 耗时: {latency:.2f}秒 | 状态码: {response.status_code} | {response.text}")
        except Exception as e:
            print(f"   [{attempt_desc}] 🚨 网络/超时异常: {e}")

def test_auto_directory_and_duplicate():
    print("="*60)
    print(f"🚀 自动批量入库与 MD5 防重测试启动")
    print(f"📂 目标扫描目录: {TEST_DIR}")
    print("="*60)
    
    if not os.path.exists(TEST_DIR):
        print(f"❌ 找不到测试目录，请确认路径是否正确: {TEST_DIR}")
        return

    # 1. 递归扫描目录及其【所有子文件夹】下的文件
    files_to_test = []
    for root_path, sub_dirs, files in os.walk(TEST_DIR):
        for f in files:
            # 顺手加个小优化：过滤掉像 .DS_Store 这样的系统隐藏文件
            if not f.startswith('.'): 
                files_to_test.append(os.path.join(root_path, f))
    
    if not files_to_test:
        print("🤷‍♂️ 测试目录下空空如也，请先放入一些测试文档（PDF/Docx/Excel/TXT等）。")
        return

    print(f"🔍 发现 {len(files_to_test)} 个待测文件，准备开始...\n")

    # 2. 遍历文件，执行“双连击”上传测试
    for idx, file_path in enumerate(files_to_test, 1):
        filename = os.path.basename(file_path)
        filesize_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        print(f"▶️ [{idx}/{len(files_to_test)}] 正在测试文件: {filename} (大小: {filesize_mb:.2f} MB)")
        
        # 第一击：全新入库（需要走完整的解析、切片、大模型 Embedding 流程）
        upload_single_file(file_path, "第一次上传 (全新解析)")
        
        # 第二击：重复入库（期望触发 MD5 拦截，实现 0 延时秒传）
        upload_single_file(file_path, "第二次上传 (测试查重)")
        print("-" * 60)

    # 3. 传完立刻提问，测试新项目是否可用
    print("\n========== 阶段 2：热更新检索测试 ==========")
    time.sleep(2)  # 给 ES 留两秒钟的倒排索引刷新时间
    question = "请用一句话总结你刚才入库的这些文档核心讲了什么？"
    
    payload = {
        "message": question,
        "project_name": PROJECT_NAME,
        "history": [],
        "top_k": 10,
        "temperature": 0.3
    }
    
    try:
        print(f"🤖 正在向【{PROJECT_NAME}】提问: {question}")
        chat_res = requests.post(CHAT_URL, json=payload, timeout=60)
        print(f"💬 大模型回答:\n{chat_res.json().get('answer', '无返回')}")
    except Exception as e:
        print(f"提问请求失败: {e}")

if __name__ == "__main__":
    test_auto_directory_and_duplicate()