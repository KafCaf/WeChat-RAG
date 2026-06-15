import gradio as gr
import requests
import traceback

# ==========================================
# 0. 配置与模拟数据
# ==========================================
API_BASE_URL = "http://127.0.0.1:6006" 

# 自定义 CSS 样式：实现马卡龙色调、毛玻璃效果、左右布局
custom_css = """
/* 全局背景：浅蓝色/粉色柔和渐变 */
.gradio-container {
    background: linear-gradient(135deg, #e0f2f1 0%, #fce4ec 50%, #fff3e0 100%) !important;
    min-height: 100vh !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}

/* 登录卡片容器 */
#auth_container {
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(15px);
    border-radius: 24px;
    box-shadow: 0 20px 50px rgba(0,0,0,0.08);
    overflow: hidden;
    max-width: 950px;
    margin: auto;
    border: 1px solid rgba(255,255,255,0.4);
}

/* 左侧品牌区颜色 */
.brand-column {
    background: linear-gradient(180deg, #fff3e0 0%, #ffe0b2 100%) !important;
    padding: 60px 40px !important;
    border-right: 1px solid rgba(0,0,0,0.05) !important;
}

/* 按钮样式：橙色主题 */
.orange-button {
    background: #ffa726 !important;
    border: none !important;
    color: white !important;
    font-weight: bold !important;
    border-radius: 10px !important;
    padding: 10px !important;
    height: 45px !important;
}
.orange-button:hover {
    background: #fb8c00 !important;
    transform: translateY(-1px);
}

/* 主业务页面容器 */
#main_page_container {
    background: white !important;
    border-radius: 20px;
    padding: 20px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.05);
}

/* 快速登录预览卡片 */
.quick-login-card {
    background: #f8f9fa;
    border-radius: 10px;
    padding: 12px 8px;
    border: 1px solid #eee;
    text-align: center;
    font-size: 11px;
}
"""

# ==========================================
# 1. 后端业务函数逻辑
# ==========================================

def login_user(username, password):
    """登录逻辑"""
    if not username or not password:
        return gr.update(visible=True), gr.update(visible=False), "⚠️ 请输入账号密码"
    try:
        payload = {"username": username, "password": password}
        res = requests.post(f"{API_BASE_URL}/login", json=payload, timeout=5)
        if res.status_code == 200:
            return gr.update(visible=False), gr.update(visible=True), f"👋 欢迎回来，{username} | 身份已核验"
        else:
            error_msg = res.json().get('detail', '验证失败')
            return gr.update(visible=True), gr.update(visible=False), f"❌ 登录失败: {error_msg}"
    except Exception as e:
        # 为了演示，如果后端没开，admin/123456 可登录
        if username == "admin" and password == "123456":
            return gr.update(visible=False), gr.update(visible=True), "👋 [演示模式] 登录成功"
        return gr.update(visible=True), gr.update(visible=False), f"🔌 服务未响应: {str(e)}"

def register_user(username, password, confirm_password):
    """注册逻辑"""
    if password != confirm_password: return "❌ 两次输入的密码不一致！"
    try:
        payload = {"username": username, "password": password}
        res = requests.post(f"{API_BASE_URL}/register", json=payload, timeout=5)
        return "✅ 注册成功！请切换到登录页。" if res.status_code == 200 else f"❌ {res.json().get('detail')}"
    except: return "🔌 连接后端失败"

def get_projects():
    """获取知识库列表"""
    try:
        res = requests.get(f"{API_BASE_URL}/projects", timeout=5)
        if res.status_code == 200:
            data = res.json()
            return data.get("projects", ["默认知识库"])
    except: pass
    return ["默认知识库"]

def upload_document(file_obj, project_name):
    """上传文档"""
    if file_obj is None: return "⚠️ 请先选择要上传的文件！"
    try:
        files = {'file': open(file_obj.name, 'rb')}
        data = {'project_name': project_name}
        res = requests.post(f"{API_BASE_URL}/upload", files=files, data=data, timeout=120)
        return "✅ 上传并解析成功！" if res.status_code == 200 else f"❌ {res.text}"
    except Exception as e: return f"❌ 出错: {str(e)}"

def chat_with_backend(message, history, project_name, top_k, temperature):
    """对话交互"""
    payload = {
        "message": message, 
        "project_name": project_name, 
        "history": [], 
        "top_k": int(top_k), 
        "temperature": float(temperature)
    }
    try:
        res = requests.post(f"{API_BASE_URL}/chat", json=payload, timeout=60)
        return res.json().get("answer", "生成内容为空") if res.status_code == 200 else f"⚠️ 错误: {res.status_code}"
    except Exception as e: return f"🔌 系统网络出错: {str(e)}"

# ==========================================
# 2. 界面布局 (UI 设计)
# ==========================================

with gr.Blocks(css=custom_css, theme=gr.themes.Soft(), title="高校餐厅订餐系统") as demo:
    
    # --- 登录与注册容器 ---
    with gr.Row(elem_id="auth_container", visible=True) as auth_page:
        
        # 左侧：品牌形象展示
        with gr.Column(scale=4, elem_classes="brand-column"):
            gr.HTML("""
                <div style="text-align: center;">
                    <div style="background: #ffa726; width: 64px; height: 64px; border-radius: 18px; 
                                margin: 40px auto 20px; display: flex; align-items: center; justify-content: center;
                                color: white; font-size: 32px; box-shadow: 0 4px 15px rgba(255,167,38,0.4);">
                        🍲
                    </div>
                    <h2 style="color: #5d4037; font-size: 24px; margin-bottom: 5px;">高校餐厅订餐系统</h2>
                    <p style="color: #8d6e63; font-size: 14px;">智慧校园 · 便捷订餐 · 美味生活</p>
                    
                    <div style="margin-top: 50px; text-align: left; padding: 0 20px; color: #8d6e63; font-size: 13px; line-height: 2.5;">
                        <p>🍲 <b>多食堂菜品</b> 在线浏览，丰富选择</p>
                        <p>🛒 <b>一键下单</b> 支持多种支付方式</p>
                        <p>🕒 <b>实时订单追踪</b> 到餐自动提醒</p>
                    </div>
                </div>
            """)

        # 右侧：登录注册表单
        with gr.Column(scale=6, variant="panel"):
            gr.Markdown("<br><h2 style='text-align: center;'>欢迎登录</h2>")
            gr.Markdown("<p style='text-align: center; color: #999; font-size: 13px; margin-bottom: 20px;'>请输入您的账号和密码</p>")
            
            with gr.Tabs():
                with gr.TabItem("🔑 账号登录"):
                    login_user_input = gr.Textbox(label="学号/账号", placeholder="admin", lines=1)
                    login_pwd_input = gr.Textbox(label="密码", placeholder="123456", type="password")
                    login_btn = gr.Button("立 即 登 录", elem_classes="orange-button")
                    login_status = gr.Markdown()
                    
                    gr.HTML("<p style='text-align: center; font-size: 12px; color: #bbb; margin-top: 20px;'>快速登录体验</p>")
                    with gr.Row():
                        gr.HTML('<div class="quick-login-card">👤 学生端<br><b>2021001</b></div>')
                        gr.HTML('<div class="quick-login-card">⚙️ 管理端<br><b>admin001</b></div>')
                        gr.HTML('<div class="quick-login-card">🍳 食堂端<br><b>canteen001</b></div>')

                with gr.TabItem("📝 注册新账号"):
                    reg_user_input = gr.Textbox(label="设置用户名")
                    reg_pwd_input = gr.Textbox(label="设置密码", type="password")
                    reg_confirm_input = gr.Textbox(label="确认密码", type="password")
                    reg_btn = gr.Button("注 册", elem_classes="orange-button")
                    reg_status = gr.Markdown()

            gr.Markdown("<p style='text-align: center; font-size: 13px; color: #999; margin-top: 20px;'>还没有账号？ <span style='color: #ffa726; cursor: pointer;'>立即注册</span></p>")

    # --- RAG 主业务容器 (登录成功后可见) ---
    with gr.Column(visible=False, elem_id="main_page_container") as main_page:
        header_welcome = gr.Markdown("### 👋 欢迎进入智能订餐助手")
        
        with gr.Row():
            # 左侧面板：控制与上传
            with gr.Column(scale=1):
                gr.Markdown("#### 📂 知识库与文档")
                projects_list = get_projects()
                project_dropdown = gr.Dropdown(choices=projects_list, value=projects_list[0], label="当前项目知识库", interactive=True)
                
                file_input = gr.File(label="上传订餐指南/菜单", file_count="single")
                upload_btn = gr.Button("上传并训练解析", variant="secondary")
                upload_status = gr.Textbox(label="系统状态", interactive=False)
                
                gr.Markdown("---")
                gr.Markdown("#### ⚙️ 智能参数")
                top_k_slider = gr.Slider(1, 5, 3, step=1, label="检索深度 (Top-K)")
                temp_slider = gr.Slider(0.1, 1.0, 0.4, step=0.1, label="生成温度")

            # 右侧面板：对话区
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(height=600, show_copy_button=True)
                gr.ChatInterface(
                    fn=chat_with_backend, 
                    chatbot=chatbot, 
                    additional_inputs=[project_dropdown, top_k_slider, temp_slider]
                )

    # ==========================================
    # 3. 交互事件绑定
    # ==========================================
    
    # 登录逻辑绑定
    login_btn.click(
        fn=login_user, 
        inputs=[login_user_input, login_pwd_input], 
        outputs=[auth_page, main_page, header_welcome]
    )
    
    # 注册逻辑绑定
    reg_btn.click(
        fn=register_user, 
        inputs=[reg_user_input, reg_pwd_input, reg_confirm_input], 
        outputs=reg_status
    )
    
    # 上传文件绑定
    upload_btn.click(
        fn=upload_document, 
        inputs=[file_input, project_dropdown], 
        outputs=upload_status
    )

# 启动程序
if __name__ == "__main__":
    demo.launch(server_port=7860, share=True)