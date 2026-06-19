// pages/index/index.js
const app = getApp()
Page({
  data: {
    inputValue: '',
    scrollToId: '',
    isLoading: false,
    messages: [{
      id: 'msg-0',
      role: 'ai',
      content: '你好！我是项目管理智能助手。请先选择知识库，然后开始提问吧！'
    }],
    projects: [],
    selectedProjectIndex: 0,
    selectedProjectName: '项目列表',
    statusBarHeight: 20,
    navBarHeight: 108,
    menuButtonRight: 16
  },

  onLoad() {
    const sysInfo = wx.getSystemInfoSync()
    const menuBtn = wx.getMenuButtonBoundingClientRect()
    this.setData({
      statusBarHeight: sysInfo.statusBarHeight,
      navBarHeight: sysInfo.statusBarHeight + 44,
      menuButtonRight: sysInfo.windowWidth - menuBtn.left + 12
    })
    this.fetchProjects()
  },

  // 快捷提问
  quickAsk(e) {
    const q = e.currentTarget.dataset.q
    if (!q) return
    this.setData({ inputValue: q })
    this.sendMessage()
  },

  fetchProjects() {
    wx.request({
      url: app.globalData.API_BASE_URL + '/projects',
      method: 'GET',
      success: (res) => {
        if (res.data && res.data.status === 'success') {
          const realProjects = res.data.projects.filter(p => p !== '全部项目 (全局搜索)')
          this.setData({
            projects: realProjects,
            selectedProjectIndex: 0,
            selectedProjectName: '项目列表'
          })
        }
      },
      fail: (err) => { console.error("拉取项目列表失败", err) }
    })
  },

  onProjectChange(e) {
    const index = e.detail.value
    const name = this.data.projects[index]
    this.setData({
      selectedProjectIndex: index,
      selectedProjectName: name
    })
    const sysMsgId = `msg-${Date.now()}`
    this.setData({
      messages: [...this.data.messages, {
        id: sysMsgId,
        role: 'system',
        content: `已切换至：${name}`
      }],
      scrollToId: 'bottom-spacer'
    })
  },

  chooseAndUploadFile() {
    if (this.data.isUploading) return
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['.pdf', '.doc', '.docx', '.txt', '.md'],
      success: (res) => {
        const file = res.tempFiles[0]
        if (file.size > 20 * 1024 * 1024) {
          wx.showToast({ title: '文件不能超过 20MB', icon: 'none' })
          return
        }
        this.uploadToServer(file)
      },
      fail: (err) => { console.log("用户取消选择文件或失败", err) }
    })
  },

  uploadToServer(file) {
    this.setData({ isUploading: true })
    wx.showLoading({ title: '文档解析入库中...', mask: true })

    const projectNameForBackend = this.data.selectedProjectName === '项目列表'
      ? '全部项目 (全局搜索)'
      : this.data.selectedProjectName

    wx.uploadFile({
      url: app.globalData.API_BASE_URL + '/upload',
      filePath: file.path,
      name: 'file',
      formData: { 'project_name': projectNameForBackend },
      success: (res) => {
        let data
        try { data = JSON.parse(res.data) } catch (e) { data = res.data }
        if (res.statusCode === 200) {
          wx.showToast({ title: '知识库更新成功！', icon: 'success' })
          const sysMsgId = `msg-${Date.now()}`
          this.setData({
            messages: [...this.data.messages, {
              id: sysMsgId,
              role: 'system',
              content: `📄 文件《${file.name}》已加入知识库，可以开始提问了`
            }],
            scrollToId: 'bottom-spacer'
          })
        } else {
          wx.showToast({ title: data.detail || '上传失败', icon: 'none' })
        }
      },
      fail: (err) => {
        console.error("上传网络异常", err)
        wx.showToast({ title: '网络连接失败', icon: 'none' })
      },
      complete: () => {
        wx.hideLoading()
        this.setData({ isUploading: false })
      }
    })
  },

  handleInput(e) {
    this.setData({ inputValue: e.detail.value })
  },

  sendMessage() {
    const text = this.data.inputValue.trim()
    if (!text || this.data.isLoading) return

    const newMsgId = `msg-${Date.now()}`
    const newUserMsg = { id: newMsgId, role: 'user', content: text }
    const loadingMsgId = `msg-loading`
    const loadingMsg = { id: loadingMsgId, role: 'ai', isLoadingBubble: true }

    this.setData({
      messages: [...this.data.messages, newUserMsg, loadingMsg],
      inputValue: '',
      scrollToId: 'bottom-spacer',
      isLoading: true
    })

    this.fetchAiResponse(text, loadingMsgId)
  },

  fetchAiResponse(userText, loadingMsgId) {
    wx.showNavigationBarLoading()
    const history = []

    const projectNameForBackend = this.data.selectedProjectName === '项目列表'
      ? '全部项目 (全局搜索)'
      : this.data.selectedProjectName

    wx.request({
      url: app.globalData.API_BASE_URL + '/chat',
      method: 'POST',
      data: {
        message: userText,
        project_name: projectNameForBackend,
        history: history,
        top_k: 3,
        temperature: 0.4
      },
      header: { 'content-type': 'application/json' },
      success: (res) => {
        if (res.statusCode === 200 && res.data.answer) {
          const aiMsgId = `msg-${Date.now()}`
          let fullAnswer = res.data.answer
          let mainContent = fullAnswer
          let refContent = ''

          let splitIndex = fullAnswer.indexOf('参考来源：')
          if (splitIndex === -1) splitIndex = fullAnswer.indexOf('参考来源:')

          if (splitIndex !== -1) {
            mainContent = fullAnswer.substring(0, splitIndex).trim()
            refContent = fullAnswer.substring(splitIndex).trim()
          }

          const newAiMsg = {
            id: aiMsgId,
            role: 'ai',
            content: mainContent,
            reference: refContent
          }

          const currentMessages = this.data.messages.filter(msg => msg.id !== loadingMsgId)
          this.setData({
            messages: [...currentMessages, newAiMsg],
            scrollToId: 'bottom-spacer'
          })
        } else {
          this.removeLoadingBubbleAndShowError('后端处理异常', loadingMsgId)
        }
      },
      fail: (err) => {
        console.error("请求失败", err)
        this.removeLoadingBubbleAndShowError('网络连接失败，请检查后端', loadingMsgId)
      },
      complete: () => {
        wx.hideNavigationBarLoading()
        this.setData({ isLoading: false })
      }
    })
  },

  removeLoadingBubbleAndShowError(errorText, loadingMsgId) {
    const currentMessages = this.data.messages.filter(msg => msg.id !== loadingMsgId)
    wx.showToast({ title: errorText, icon: 'none' })
    this.setData({ messages: currentMessages })
  }
})
