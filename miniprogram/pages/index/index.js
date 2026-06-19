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
    uploadMode: null,
    newProjectName: '',
    keyboardHeight: 0
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
    this.fetchProjects()
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
          self.fetchProjects()
          if (self.data.uploadMode === 'new') {
            // 新建项目：等列表刷新后自动选中
            setTimeout(() => {
              const projects = self.data.projects
              const idx = projects.indexOf(projectName)
              if (idx >= 0) self.setData({ selectedProjectIndex: idx, selectedProjectName: projectName })
            }, 500)
          }
        } else {
          wx.showToast({ title: data.detail || '上传失败', icon: 'none' })
        }
      },
      fail() { wx.showToast({ title: '网络连接失败', icon: 'none' }) },
      complete() { wx.hideLoading(); self.setData({ isUploading: false, uploadMode: null, newProjectName: '' }) }
    })
  },

  // ---- 管理 ----
  showManageOptions() {
    const self = this
    wx.showActionSheet({
      itemList: ['查看文档列表', '删除当前知识库'],
      success(res) {
        if (res.tapIndex === 0) {
          self.showFileList()
        } else {
          self.confirmDeleteProject()
        }
      }
    })
  },

  showFileList() {
    const self = this
    const pName = this.data.selectedProjectName
    wx.request({
      url: app.globalData.API_BASE_URL + '/files?project_name=' + encodeURIComponent(pName),
      success(res) {
        if (!res.data || !res.data.files || res.data.files.length === 0) {
          wx.showToast({ title: '知识库暂无文档', icon: 'none' })
          return
        }
        const names = res.data.files.map(f => {
          const raw = f.split('/').pop()
          // 微信上传的临时文件名，用 ES 里存的真实文件名
          return raw
        })
        wx.showActionSheet({
          itemList: names.map(n => '删除: ' + n),
          success(r) {
            const file = res.data.files[r.tapIndex]
            wx.showModal({
              title: '确认删除',
              content: `将删除「${file.split('/').pop()}」`,
              confirmText: '删除',
              confirmColor: '#ef4444',
              success(mr) {
                if (mr.confirm) {
                  wx.request({
                    url: app.globalData.API_BASE_URL + '/files?filename=' + encodeURIComponent(file) + '&project_name=' + encodeURIComponent(pName),
                    method: 'DELETE',
                    success() {
                      wx.showToast({ title: '已删除', icon: 'success' })
                      self.setData({ messages: [...self.data.messages, { id: `msg-${Date.now()}`, role: 'system', content: `文档已删除` }], scrollToId: 'bottom-spacer' })
                    }
                  })
                }
              }
            })
          }
        })
      }
    })
  },

  confirmDeleteProject() {
    const pName = this.data.selectedProjectName
    const self = this
    wx.showModal({
      title: '删除知识库',
      content: `确定删除「${pName}」及其所有文档？此操作不可撤销。`,
      success(res) {
        if (res.confirm) {
          wx.request({
            url: app.globalData.API_BASE_URL + '/projects/' + encodeURIComponent(pName),
            method: 'DELETE',
            success() {
              wx.showToast({ title: '已删除', icon: 'success' })
              self.setData({ selectedProjectIndex: 0, selectedProjectName: '项目列表', messages: [] })
              self.fetchProjects()
            }
          })
        }
      }
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
      data: { message: userText, project_name: pName, history: [], top_k: 15, temperature: 0.1 },
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
