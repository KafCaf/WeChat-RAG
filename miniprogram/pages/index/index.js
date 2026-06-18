// pages/index/index.js
const app = getApp()
Page({
  data: {
    inputValue: '',
    scrollToId: '',
    isLoading: false,
    messages: [
      {
        id: 'msg-0',
        role: 'ai',
        content: '你好！我是项目管理智能助手。请先选择你要查询的项目知识库，然后开始提问吧！'
      }
    ],
    // 🌟 修改这里：把初始的数组清空
    projects: [], 
    selectedProjectIndex: 0,
    selectedProjectName: '项目列表' // 保持这个作为外面的提示文字
  },

  onLoad() {
    // 🌟 页面加载时拉取后端的项目列表
    this.fetchProjects();
  },

  // 🌟 新增：调用后端 GET /projects 接口
  fetchProjects() {
    wx.request({
      url: app.globalData.API_BASE_URL + '/projects', 
      method: 'GET',
      success: (res) => {
        if (res.data && res.data.status === 'success') {
          
          // 🌟 核心修复：把后端返回的 "全部项目 (全局搜索)" 直接过滤掉，不让它进入下拉选项
          const realProjects = res.data.projects.filter(p => p !== '全部项目 (全局搜索)');

          this.setData({
            projects: realProjects,
            // 列表加载完后，外面依然显示“项目列表”四个字
            selectedProjectIndex: 0,
            selectedProjectName: '项目列表'
          });
        }
      },
      fail: (err) => {
        console.error("拉取项目列表失败", err);
      }
    });
  },

 // 🌟 修改前：
  // role: 'ai',
  // content: `[系统提示] 已将知识库切换至：${this.data.projects[index]}`
  
  // ✅ 修改后：
  onProjectChange(e) {
    const index = e.detail.value;
    this.setData({
      selectedProjectIndex: index,
      selectedProjectName: this.data.projects[index]
    });
    
    const sysMsgId = `msg-${Date.now()}`;
    this.setData({
      messages: [...this.data.messages, {
        id: sysMsgId,
        role: 'system', // 🌟 关键修改1：改成 system
        content: `已将知识库切换至：${this.data.projects[index]}` // 🌟 去掉了多余的前缀
      }],
      scrollToId: 'bottom-spacer'
    });
  },
  // 🌟 新增：触发选择微信文件
  chooseAndUploadFile() {
    if (this.data.isUploading) return;

    wx.chooseMessageFile({
      count: 1, // 每次只允许传1个文件
      type: 'file', // 可以选择任何文件
      extension: ['.pdf', '.doc', '.docx', '.txt', '.md'], // 限制文件格式
      success: (res) => {
        const file = res.tempFiles[0];
        // 限制大小，比如不能超过 20MB
        if (file.size > 20 * 1024 * 1024) {
          wx.showToast({ title: '文件不能超过 20MB', icon: 'none' });
          return;
        }
        this.uploadToServer(file);
      },
      fail: (err) => {
        console.log("用户取消选择文件或失败", err);
      }
    });
  },

  // 🌟 新增：真正发送文件到 AutoDL 后端
  
  uploadToServer(file) {
    this.setData({ isUploading: true });
    wx.showLoading({ title: '文档解析入库中...', mask: true });

    const projectNameForBackend = this.data.selectedProjectName === '项目列表' 
      ? '全部项目 (全局搜索)' 
      : this.data.selectedProjectName;

    wx.uploadFile({
      url: app.globalData.API_BASE_URL + '/upload',
      filePath: file.path,
      name: 'file',
      formData: {
        'project_name': projectNameForBackend
      },
      // 1. 成功回调
      success: (res) => {
        let data;
        try { data = JSON.parse(res.data); } catch (e) { data = res.data; }

        if (res.statusCode === 200) {
          wx.showToast({ title: '知识库更新成功！', icon: 'success' });
          const sysMsgId = `msg-${Date.now()}`;
          this.setData({
            messages: [...this.data.messages, {
              id: sysMsgId,
              role: 'system', // 🌟 变成系统消息
              content: `📄 文件《${file.name}》已加入知识库，可以开始提问了` 
            }],
            scrollToId: 'bottom-spacer'
          });
        } else {
          wx.showToast({ title: data.detail || '上传失败', icon: 'none' });
        }
      }, // <-- success 到这里干净地结束
      
      // 2. 失败回调 (和 success 是平级的兄弟关系)
      fail: (err) => {
        console.error("上传网络异常", err);
        wx.showToast({ title: '网络连接失败', icon: 'none' });
      },
      
      // 3. 完成回调 (无论成功失败都会走这里解开按钮锁)
      complete: () => {
        wx.hideLoading();
        this.setData({ isUploading: false });
      }
    });
  },

  handleInput(e) {
    this.setData({ inputValue: e.detail.value });
  },

  sendMessage() {
    const text = this.data.inputValue.trim();
    if (!text || this.data.isLoading) return;

    const newMsgId = `msg-${Date.now()}`;
    const newUserMsg = { id: newMsgId, role: 'user', content: text };

    const loadingMsgId = `msg-loading`;
    const loadingMsg = { id: loadingMsgId, role: 'ai', isLoadingBubble: true };

    this.setData({
      messages: [...this.data.messages, newUserMsg, loadingMsg],
      inputValue: '',
      scrollToId: 'bottom-spacer',
      isLoading: true
    });

    this.fetchAiResponse(text, loadingMsgId);
  },

  fetchAiResponse(userText, loadingMsgId) {
    wx.showNavigationBarLoading(); 
    const history = []; 

    // 🌟 核心修改1：在这里做个判断。如果前端选的是"项目列表"，发给后端时就还原成"全部项目 (全局搜索)"
    const projectNameForBackend = this.data.selectedProjectName === '项目列表' 
      ? '全部项目 (全局搜索)' 
      : this.data.selectedProjectName;

    wx.request({
      url: app.globalData.API_BASE_URL + '/chat',
      method: 'POST',
      data: {
        message: userText,
        // 🌟 核心修改2：把原来的 this.data.selectedProjectName 替换成我们上面转换好的变量
        project_name: projectNameForBackend, 
        history: history,
        top_k: 3,         
        temperature: 0.4  
      },
      header: {
        'content-type': 'application/json' 
      },
      success: (res) => {
        if (res.statusCode === 200 && res.data.answer) {
          const aiMsgId = `msg-${Date.now()}`;
          
          // 🌟 核心切分逻辑开始
          let fullAnswer = res.data.answer;
          let mainContent = fullAnswer;
          let refContent = '';
          
          // 寻找“参考来源：”或者英文冒号的“参考来源:”
          let splitIndex = fullAnswer.indexOf('参考来源：');
          if (splitIndex === -1) {
            splitIndex = fullAnswer.indexOf('参考来源:');
          }
          
          // 如果找到了，就把文章劈成两半
          if (splitIndex !== -1) {
            mainContent = fullAnswer.substring(0, splitIndex).trim(); // 正文部分
            refContent = fullAnswer.substring(splitIndex).trim();     // 来源部分
          }
          // 🌟 核心切分逻辑结束

          const newAiMsg = { 
            id: aiMsgId, 
            role: 'ai', 
            content: mainContent, // 存入正文
            reference: refContent // 🌟 新增：存入参考来源
          };
          
          const currentMessages = this.data.messages.filter(msg => msg.id !== loadingMsgId);

          this.setData({
            messages: [...currentMessages, newAiMsg],
            scrollToId: 'bottom-spacer'
          });
        } else {
          this.removeLoadingBubbleAndShowError('后端处理异常', loadingMsgId);
        }
      },
      fail: (err) => {
        console.error("请求失败", err);
        this.removeLoadingBubbleAndShowError('网络连接失败，请检查后端', loadingMsgId);
      },
      complete: () => {
        wx.hideNavigationBarLoading();
        this.setData({ isLoading: false });
      }
    }); 
  },
  removeLoadingBubbleAndShowError(errorText, loadingMsgId) {
    const currentMessages = this.data.messages.filter(msg => msg.id !== loadingMsgId);
    wx.showToast({ title: errorText, icon: 'none' });
    this.setData({ messages: currentMessages });
  }
});