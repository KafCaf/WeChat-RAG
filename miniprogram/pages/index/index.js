const app = getApp()
Page({
  data: {
    inputValue: '',
    scrollToId: '',
    isLoading: false,
    messages: [],
    projects: [],
    currentProject: '',
    statusBarHeight: 20,
    navBarHeight: 108,
    menuButtonRight: 16,
    newProjectName: '',
    keyboardHeight: 0,
    token: '',
    conversations: [],
    conversationId: null
  },

  onLoad() {
    const sysInfo = wx.getSystemInfoSync()
    const menuBtn = wx.getMenuButtonBoundingClientRect()
    this.setData({
      statusBarHeight: sysInfo.statusBarHeight,
      navBarHeight: sysInfo.statusBarHeight + 44,
      menuButtonRight: sysInfo.windowWidth - menuBtn.left + 12
    })
    const self = this
    wx.onKeyboardHeightChange(res => { self.setData({ keyboardHeight: res.height }) })
    this.wxLogin()
  },

  // ---- 微信登录 ----
  wxLogin() {
    const cached = wx.getStorageSync('rag_token')
    if (cached) { this.setData({ token: cached }); this.fetchProjects(); return }
    const self = this
    wx.login({
      success(res) {
        if (res.code) {
          wx.request({
            url: app.globalData.API_BASE_URL + '/wx-login', method: 'POST',
            data: { code: res.code },
            success(r) {
              if (r.data && r.data.token) {
                wx.setStorageSync('rag_token', r.data.token)
                self.setData({ token: r.data.token })
                self.fetchProjects()
              }
            }
          })
        }
      }
    })
  },

  // ---- 首页 ----
  fetchProjects() {
    wx.request({
      url: app.globalData.API_BASE_URL + '/projects',
      success: (res) => {
        if (res.data && res.data.status === 'success') {
          const list = res.data.projects.filter(p => p !== '全部项目 (全局搜索)')
          this.setData({ projects: list })
        }
      }
    })
  },

  enterProject(e) {
    const name = e.currentTarget.dataset.name
    this.setData({ currentProject: name, messages: [], conversationId: null })
    this.fetchConversations()
  },

  goHome() {
    this.setData({ currentProject: '', messages: [], conversations: [], conversationId: null })
  },

  longPressProject(e) {
    const name = e.currentTarget.dataset.name
    this._manageProject(name)
  },

  _manageProject(projectName) {
    const self = this
    wx.showActionSheet({
      itemList: ['查看/删除文档', '删除项目'],
      success(r) {
        if (r.tapIndex === 0) { self._showProjectFiles(projectName) }
        else { self._confirmDeleteProject(projectName) }
      }
    })
  },

  _showProjectFiles(projectName) {
    const self = this
    wx.request({
      url: app.globalData.API_BASE_URL + '/files?project_name=' + encodeURIComponent(projectName),
      success(res) {
        if (!res.data || !res.data.files || !res.data.files.length) { wx.showToast({ title: '暂无文档', icon: 'none' }); return }
        wx.showActionSheet({
          itemList: res.data.files.map(f => '删除: ' + f),
          success(r) {
            const file = res.data.files[r.tapIndex]
            wx.showModal({
              title: '确认删除', content: '将删除「' + file + '」', confirmText: '删除', confirmColor: '#ef4444',
              success(mr) {
                if (mr.confirm) {
                  wx.request({
                    url: app.globalData.API_BASE_URL + '/files?filename=' + encodeURIComponent(file) + '&project_name=' + encodeURIComponent(projectName),
                    method: 'DELETE',
                    success() { wx.showToast({ title: '已删除', icon: 'success' }); self.fetchProjects() }
                  })
                }
              }
            })
          }
        })
      }
    })
  },

  _confirmDeleteProject(projectName) {
    const self = this
    wx.showModal({
      title: '删除项目', content: '确定删除「' + projectName + '」？', confirmColor: '#ef4444',
      success(r) {
        if (r.confirm) {
          wx.request({
            url: app.globalData.API_BASE_URL + '/projects/' + encodeURIComponent(projectName), method: 'DELETE',
            success() { wx.showToast({ title: '已删除', icon: 'success' }); self.fetchProjects() }
          })
        }
      }
    })
  },

  homeStartUpload() { this.startUpload() },

  // ---- 会话 ----
  fetchConversations() {
    if (!this.data.token || !this.data.currentProject) return
    const self = this
    wx.request({
      url: app.globalData.API_BASE_URL + '/conversations?token=' + self.data.token + '&project_name=' + encodeURIComponent(self.data.currentProject),
      success(res) {
        if (res.data && res.data.conversations) self.setData({ conversations: res.data.conversations })
      }
    })
  },

  showHistory() {
    const list = this.data.conversations
    const self = this
    wx.showActionSheet({
      itemList: ['+ 新建对话', ...list.map(c => c.title + (c.id === this.data.conversationId ? ' ✓' : ''))],
      success(r) {
        if (r.tapIndex === 0) { self.setData({ conversationId: null, messages: [] }); return }
        const conv = list[r.tapIndex - 1]
        self.switchConversation(conv.id)
      }
    })
  },

  switchConversation(convId) {
    const self = this
    wx.request({
      url: app.globalData.API_BASE_URL + '/conversations/' + convId + '?token=' + self.data.token,
      success(res) {
        if (res.data && res.data.history) {
          const msgs = []
          for (const h of res.data.history) msgs.push({ id: `msg-${Date.now()}`, role: h.role === 'assistant' ? 'ai' : h.role, content: h.content })
          self.setData({ messages: msgs, conversationId: convId, scrollToId: 'bottom-spacer' })
        }
      }
    })
  },

  // ---- 上传 ----
  startUpload() {
    const self = this
    const isHome = !this.data.currentProject
    const itemList = isHome ? ['上传到现有知识库', '新建知识库并上传'] : ['上传到当前知识库', '上传到新建知识库']
    wx.showActionSheet({
      itemList,
      success(r) {
        if (r.tapIndex === 0) {
          if (isHome) { self._pickProjectThenUpload() }
          else { self._pickFile('existing') }
        } else {
          wx.showModal({
            title: '新建知识库', editable: true, placeholderText: '输入知识库名称',
            success(mr) {
              if (mr.confirm && mr.content) self._pickFile('new', mr.content.trim())
            }
          })
        }
      }
    })
  },

  _pickProjectThenUpload() {
    const self = this
    wx.showActionSheet({
      itemList: this.data.projects,
      success(r) {
        const name = self.data.projects[r.tapIndex]
        self.setData({ currentProject: name })
        self._pickFile('existing')
      }
    })
  },

  _pickFile(mode, newProjectName) {
    wx.chooseMessageFile({
      count: 1, type: 'file', extension: ['.pdf', '.doc', '.docx', '.txt', '.md'],
      success: (res) => {
        const file = res.tempFiles[0]
        if (file.size > 20*1024*1024) { wx.showToast({ title: '文件不超过 20MB', icon: 'none' }); return }
        const originName = file.name
        wx.showModal({
          title: '文档命名', editable: true, content: originName, placeholderText: originName,
          success(mr) {
            let finalName = (mr.confirm && mr.content) ? mr.content.trim() : originName
            // 自动保留原始文件后缀
            const ext = originName.slice(originName.lastIndexOf('.'))
            if (!finalName.endsWith(ext)) finalName += ext
            file.customName = finalName
            if (newProjectName) self.setData({ newProjectName: newProjectName })
            self.uploadToServer(file, mode, newProjectName)
          }
        })
      }
    })
  },

  uploadToServer(file, mode, newProjectName) {
    wx.showLoading({ title: '入库中...', mask: true })
    const projectName = newProjectName || this.data.currentProject
    const self = this

    wx.uploadFile({
      url: app.globalData.API_BASE_URL + '/upload', filePath: file.path, name: 'file',
      formData: { project_name: projectName, custom_filename: file.customName || '' },
      success(res) {
        let data
        try { data = JSON.parse(res.data) } catch (e) { data = res.data }
        if (res.statusCode === 200) {
          wx.showToast({ title: '入库成功', icon: 'success' })
          self.fetchProjects()
          if (newProjectName) {
            // 新建项目：自动跳转到新知识库
            setTimeout(() => self.setData({ currentProject: projectName, messages: [], conversationId: null, newProjectName: '' }), 500)
          }
        } else { wx.showToast({ title: data.detail || '失败', icon: 'none' }) }
      },
      fail() { wx.showToast({ title: '网络异常', icon: 'none' }) },
      complete() { wx.hideLoading() }
    })
  },

  // ---- 聊天 ----
  handleInput(e) { this.setData({ inputValue: e.detail.value }) },

  sendMessage() {
    const text = this.data.inputValue.trim()
    if (!text || this.data.isLoading || !this.data.currentProject) return
    const loading = { id: 'msg-loading', role: 'ai', isLoadingBubble: true }
    this.setData({
      messages: [...this.data.messages, { id: `msg-${Date.now()}`, role: 'user', content: text }, loading],
      inputValue: '', scrollToId: 'bottom-spacer', isLoading: true
    })
    this.fetchAiResponse(text, 'msg-loading')
  },

  fetchAiResponse(userText, loadingMsgId) {
    wx.showNavigationBarLoading()
    const self = this
    wx.request({
      url: app.globalData.API_BASE_URL + '/chat', method: 'POST',
      header: { 'content-type': 'application/json' },
      data: { message: userText, project_name: self.data.currentProject, history: [], top_k: 15, temperature: 0.1, token: self.data.token, conversation_id: self.data.conversationId },
      timeout: 60000,
      success(res) {
        if (res.statusCode === 200 && res.data.answer) {
          const msgs = self.data.messages.filter(m => m.id !== loadingMsgId)
          const update = { messages: [...msgs, { id: `msg-${Date.now()}`, role: 'ai', content: res.data.answer }], scrollToId: 'bottom-spacer' }
          if (res.data.conversation_id && res.data.conversation_id !== self.data.conversationId) {
            update.conversationId = res.data.conversation_id
            self.fetchConversations()
          }
          self.setData(update)
        } else {
          self.setData({ messages: self.data.messages.filter(m => m.id !== loadingMsgId) })
          wx.showToast({ title: '后端异常', icon: 'none' })
        }
      },
      fail() {
        self.setData({ messages: self.data.messages.filter(m => m.id !== loadingMsgId) })
        wx.showToast({ title: '网络异常', icon: 'none' })
      },
      complete() { wx.hideNavigationBarLoading(); self.setData({ isLoading: false }) }
    })
  }
})
