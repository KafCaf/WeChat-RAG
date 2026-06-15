import gradio as gr
import requests
import traceback

API_BASE_URL = "http://127.0.0.1:6006" 

# ==========================================
# 0. 模拟用户数据库 (测试用)
# ==========================================
# 在实际工程中，这里应该调用 FastAPI 后端的数据库接口
USER_DB = {
    "admin": "123456" 
}

# ==========================================
# 🌟 真实的用户验证逻辑 (对接 FastAPI 后端)
# ==========================================

def register_user(username, password, confirm_password):
    """通过 API 发送真实的注册请求"""
    if not username or not password:
        return "⚠️ 用户名和密码不能为空！"
    if password != confirm_password:
        return "❌ 两次输入的密码不一致！"
    
    try:
        # 向后端的 /register 接口发送 POST 请求
        payload = {"username": username, "password": password}
        res = requests.post(f"{API_BASE_URL}/register", json=payload, timeout=5)
        
        if res.status_code == 200:
            return f"✅ 注册成功！欢迎你，{username}。请切换到左侧登录标签进行登录。"
        else:
            # 捕获后端返回的错误信息（如“该用户名已被注册”）
            return f"❌ 注册失败: {res.json().get('detail', '未知错误')}"
    except Exception as e:
        return f"🔌 网络连接失败: {str(e)}"


def login_user(username, password):
    """通过 API 发送真实的登录请求并控制页面流转"""
    if not username or not password:
        return gr.update(visible=True), gr.update(visible=False), "⚠️ 请输入用户名和密码"

    try:
        # 向后端的 /login 接口发送 POST 请求
        payload = {"username": username, "password": password}
        res = requests.post(f"{API_BASE_URL}/login", json=payload, timeout=5)
        
        if res.status_code == 200:
            # 登录成功：隐藏登录容器，显示主程序容器，更新顶部的欢迎语
            return gr.update(visible=False), gr.update(visible=True), f"👋 欢迎回来，{username} | 身份已核验"
        else:
            # 登录失败：拿到后端的报错信息（密码错误或用户不存在）
            error_msg = res.json().get('detail', '验证失败')
            return gr.update(visible=True), gr.update(visible=False), f"❌ 登录失败: {error_msg}"
            
    except Exception as e:
        return gr.update(visible=True), gr.update(visible=False), f"🔌 后端服务无响应: {str(e)}"

# （下面的界面布局代码完全不需要变动，只需更新这两个核心函数即可）

# ==========================================
# 1. 后端接口调用封装 (保持不变)
# ==========================================
def get_projects():
    try:
        res = requests.get(f"{API_BASE_URL}/projects", timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data.get("status") == "success":
                return data.get("projects", ["全部项目 (全局搜索)"])
    except:
        pass
    return ["全部项目 (全局搜索)"]

def upload_document(file_obj, project_name):
    if file_obj is None: return "⚠️ 请先选择要上传的文件！"
    files = {'file': open(file_obj.name, 'rb')}
    data = {'project_name': project_name}
    try:
        res = requests.post(f"{API_BASE_URL}/upload", files=files, data=data, timeout=120)
        if res.status_code == 200: return f"✅ 文件上传成功！已存入【{project_name}】。"
        else: return f"❌ 上传失败: {res.json().get('detail', res.text)}"
    except Exception as e:
        return f"❌ 网络异常: {str(e)}"

def chat_with_backend(message, history, project_name, top_k, temperature):
    payload = {"message": message, "project_name": project_name, "history": [], "top_k": int(top_k), "temperature": float(temperature)}
    try:
        res = requests.post(f"{API_BASE_URL}/chat", json=payload, timeout=60)
        if res.status_code == 200: return res.json().get("answer", "生成内容为空")
        else: return f"⚠️ 后端报错: HTTP {res.status_code}"
    except Exception as e:
        return f"🔌 系统网络出错: {str(e)}"

# ==========================================
# 2. 界面布局与路由体系
# ==========================================
custom_theme = gr.themes.Soft(primary_hue="blue", secondary_hue="indigo")

with gr.Blocks(theme=custom_theme, title="项目管理智能问答系统") as demo:
    
    # 顶部全局标题
    gr.HTML("<h1 style='text-align: center; margin-bottom: 1rem; margin-top: 2rem;'>🏢 项目管理 RAG 智能协同平台</h1>")
    
    # 用于显示登录后的欢迎语
    header_welcome = gr.Markdown("### 请先登录验证身份", elem_id="welcome_text")

    # ---------------------------------------------------
    # 🔒 页面 A：登录与注册容器 (初始状态为可见)
    # ---------------------------------------------------
    with gr.Column(visible=True) as auth_page:
        with gr.Row():
            # 用一个空白列把登录框挤到中间，更好看
            gr.Column(scale=1)
            with gr.Column(scale=2):
                with gr.Tabs():
                    # 登录选项卡
                    with gr.TabItem("🔑 账号登录"):
                        login_user_input = gr.Textbox(label="用户名", placeholder="请输入用户名 (测试账号: admin)")
                        login_pwd_input = gr.Textbox(label="密码", type="password", placeholder="请输入密码")
                        login_btn = gr.Button("立 即 登 录", variant="primary")
                        login_status = gr.Markdown()
                    
                    # 注册选项卡
                    with gr.TabItem("📝 注册新账号"):
                        reg_user_input = gr.Textbox(label="设置用户名")
                        reg_pwd_input = gr.Textbox(label="设置密码", type="password")
                        reg_confirm_input = gr.Textbox(label="确认密码", type="password")
                        reg_btn = gr.Button("注 册")
                        reg_status = gr.Markdown()
            gr.Column(scale=1)

    # ---------------------------------------------------
    # 🔓 页面 B：RAG 主业务容器 (初始状态为隐藏)
    # ---------------------------------------------------
    with gr.Column(visible=False) as main_page:
        with gr.Row():
            # 左侧控制面板
            with gr.Column(scale=1):
                gr.Markdown("### 📂 知识库管理")
                projects_list = get_projects()
                project_dropdown = gr.Dropdown(choices=projects_list, value=projects_list[0] if projects_list else "全部项目 (全局搜索)", label="当前项目知识库", interactive=True)
                
                gr.Markdown("---")
                gr.Markdown("### 📤 补充项目资料")
                file_input = gr.File(label="上传文档至当前项目", file_count="single")
                upload_btn = gr.Button("开始上传解析", variant="primary")
                upload_status = gr.Textbox(label="系统状态", interactive=False)
                upload_btn.click(fn=upload_document, inputs=[file_input, project_dropdown], outputs=[upload_status])

                gr.Markdown("---")
                gr.Markdown("### ⚙️ 问答参数控制")
                top_k_slider = gr.Slider(minimum=1, maximum=5, value=3, step=1, label="检索文档数量 (Top-K)")
                temp_slider = gr.Slider(minimum=0.1, maximum=1.0, value=0.4, step=0.1, label="回答发散度 (Temperature)")
                
            # 右侧主聊天区
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(height=650, show_copy_button=True, avatar_images=(None, "https://cdn-icons-png.flaticon.com/512/8649/8649596.png"))
                gr.ChatInterface(fn=chat_with_backend, chatbot=chatbot, additional_inputs=[project_dropdown, top_k_slider, temp_slider], theme=custom_theme)

    # ==========================================
    # 3. 绑定交互事件
    # ==========================================
    # 点击注册按钮 -> 触发 register_user 函数 -> 输出提示信息
    reg_btn.click(
        fn=register_user, 
        inputs=[reg_user_input, reg_pwd_input, reg_confirm_input], 
        outputs=reg_status
    )

    # 点击登录按钮 -> 触发 login_user 函数 -> 控制两个大容器的显示/隐藏
    login_btn.click(
        fn=login_user, 
        inputs=[login_user_input, login_pwd_input], 
        outputs=[auth_page, main_page, header_welcome]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=True)