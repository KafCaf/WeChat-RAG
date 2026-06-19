const app = getApp()
Page({
  data: {
    inputValue: '',
    scrollToId: '',
    isLoading: false,
    messages: [],
    projects: [],
    selectedProjectIndex: 0,
    selectedProjectName: '项目列表',
    statusBarHeight: 20,
    navBarHeight: 108,
    menuButtonRight: 16,
    suggestQuestions: [],
    uploadMode: null,
    newProjectName: ''
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

  // ---- 推荐问题 ----
  fetchSuggestQuestions(project) {
    if (!project || project === '项目列表') return
    const cacheKey = `suggest_${project}`
    const cached = wx.getStorageSync(cacheKey)
    if (cached && cached.length) {
      this.setData({ suggestQuestions: cached })
      return
    }
    const self = this
    wx.request({
      url: app.globalData.API_BASE_URL + '/suggest-questions?project_name=' + encodeURIComponent(project),
      timeout: 30000,
      success(res) {
        if (res.data && res.data.questions) {
          wx.setStorageSync(cacheKey, res.data.questions)
          self.setData({ suggestQuestions: res.data.questions })
        }
      }
    })
  },

  // ---- 快捷提问 ----
  quickAsk(e) {
    const q = e.currentTarget.dataset.q
    if (!q) return
    this.setData({ inputValue: q })
    this.sendMessage()
  },

  // ---- 项目列表 ----
  fetchProjects() {
    wx.request({
      url: app.globalData.API_BASE_URL + '/projects',
      success: (res) => {
        console.log('projects response:', res.statusCode, JSON.stringify(res.data).substring(0, 200))
        if (res.data && res.data.status === 'success') {
          const list = res.data.projects.filter(p => p !== '全部项目 (全局搜索)')
          console.log('projects list:', list)
          this.setData({ projects: list, selectedProjectIndex: 0, selectedProjectName: '项目列表' })
        }
      },
      fail: (err) => { console.error('projects fail:', JSON.stringify(err)) }
    })
  },

  onProjectChange(e) {
    const index = e.detail.value
    const name = this.data.projects[index]
    this.setData({ selectedProjectIndex: index, selectedProjectName: name })
    this.setData({
      messages: [...this.data.messages, {
        id: `msg-${Date.now()}`, role: 'system', content: `已切换至：${name}`
      }],
      scrollToId: 'bottom-spacer'
    })
    this.fetchSuggestQuestions(name)
  },

  // ---- 上传流程 ----
  startUpload() {
    const self = this
    wx.showActionSheet({
      itemList: ['上传到当前知识库', '上传到新建知识库'],
      success(res) {
        if (res.tapIndex === 0) {
          self.chooseFile()
        } else {
          // 新建项目：先弹窗输入名称
          wx.showModal({
            title: '新建知识库',
            editable: true,
            placeholderText: '输入知识库名称',
            success(modalRes) {
              if (modalRes.confirm && modalRes.content) {
                self.setData({ newProjectName: modalRes.content.trim() })
                self._chooseFileForNew(modalRes.content.trim())
              }
            }
          })
        }
      }
    })
  },

  chooseFile() {
    wx.chooseMessageFile({
      count: 1, type: 'file',
      extension: ['.pdf', '.doc', '.docx', '.txt', '.md'],
      success: (res) => {
        const file = res.tempFiles[0]
        if (file.size > 20 * 1024 * 1024) {
          wx.showToast({ title: '文件不能超过 20MB', icon: 'none' })
          return
        }
        this.setData({ uploadMode: 'existing' })
        this.uploadToServer(file)
      }
    })
  },

  _chooseFileForNew(projectName) {
    wx.chooseMessageFile({
      count: 1, type: 'file',
      extension: ['.pdf', '.doc', '.docx', '.txt', '.md'],
      success: (res) => {
        const file = res.tempFiles[0]
        if (file.size > 20 * 1024 * 1024) {
          wx.showToast({ title: '文件不能超过 20MB', icon: 'none' })
          return
        }
        this.setData({ uploadMode: 'new' })
        this.uploadToServer(file)
      }
    })
  },

  uploadToServer(file) {
    this.setData({ isUploading: true })
    wx.showLoading({ title: '文档解析入库中...', mask: true })

    let projectName
    if (this.data.uploadMode === 'new' && this.data.newProjectName) {
      projectName = this.data.newProjectName
    } else {
      projectName = this.data.selectedProjectName === '项目列表'
        ? '全部项目 (全局搜索)'
        : this.data.selectedProjectName
    }

    const self = this
    wx.uploadFile({
      url: app.globalData.API_BASE_URL + '/upload',
      filePath: file.path, name: 'file',
      timeout: 120000,
      formData: { 'project_name': projectName },
      success(res) {
        let data
        try { data = JSON.parse(res.data) } catch (e) { data = res.data }
        if (res.statusCode === 200) {
          wx.showToast({ title: '入库成功', icon: 'success' })
          wx.removeStorageSync(`suggest_${projectName}`)
          self.setData({
            messages: [...self.data.messages, {
              id: `msg-${Date.now()}`, role: 'system',
              content: `文件《${file.name}》已加入知识库`
            }],
            scrollToId: 'bottom-spacer',
            uploadMode: null, newProjectName: ''
          })
          if (self.data.uploadMode === 'new') self.fetchProjects()
          self.fetchSuggestQuestions(projectName)
        } else {
          wx.showToast({ title: data.detail || '上传失败', icon: 'none' })
        }
      },
      fail() { wx.showToast({ title: '网络连接失败', icon: 'none' }) },
      complete() { wx.hideLoading(); self.setData({ isUploading: false, uploadMode: null, newProjectName: '' }) }
    })
  },

  // ---- 聊天 ----
  handleInput(e) { this.setData({ inputValue: e.detail.value }) },

  sendMessage() {
    const text = this.data.inputValue.trim()
    if (!text || this.data.isLoading) return
    const newUser = { id: `msg-${Date.now()}`, role: 'user', content: text }
    const loading = { id: 'msg-loading', role: 'ai', isLoadingBubble: true }
    this.setData({
      messages: [...this.data.messages, newUser, loading],
      inputValue: '', scrollToId: 'bottom-spacer', isLoading: true
    })
    this.fetchAiResponse(text, 'msg-loading')
  },

  fetchAiResponse(userText, loadingMsgId) {
    wx.showNavigationBarLoading()
    const pName = this.data.selectedProjectName === '项目列表'
      ? '全部项目 (全局搜索)' : this.data.selectedProjectName

    const self = this
    wx.request({
      url: app.globalData.API_BASE_URL + '/chat',
      method: 'POST',
      timeout: 60000,
      header: { 'content-type': 'application/json' },
      data: { message: userText, project_name: pName, history: [], top_k: 3, temperature: 0.4 },
      success(res) {
        if (res.statusCode === 200 && res.data.answer) {
          const msgs = self.data.messages.filter(m => m.id !== loadingMsgId)
          self.setData({
            messages: [...msgs, { id: `msg-${Date.now()}`, role: 'ai', content: res.data.answer }],
            scrollToId: 'bottom-spacer'
          })
        } else {
          self.setData({ messages: self.data.messages.filter(m => m.id !== loadingMsgId) })
          wx.showToast({ title: '后端处理异常', icon: 'none' })
        }
      },
      fail() {
        self.setData({ messages: self.data.messages.filter(m => m.id !== loadingMsgId) })
        wx.showToast({ title: '网络连接失败', icon: 'none' })
      },
      complete() { wx.hideNavigationBarLoading(); self.setData({ isLoading: false }) }
    })
  }
})
