import React, { useState, useEffect, useRef } from 'react';
import { Send, User, Cpu, Lock, Loader2, LogOut, Database, FolderGit2, UploadCloud, UserPlus, Sparkles, MessageSquare } from 'lucide-react';

// API 地址留空，适配 FastAPI 挂载模式
const API_BASE = ''; 

export default function App() {
  // --- 1. 核心状态管理 ---
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [username, setUsername] = useState(localStorage.getItem('username') || '');
  
  const [loginUser, setLoginUser] = useState('');
  const [loginPwd, setLoginPwd] = useState('');
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [isRegisterMode, setIsRegisterMode] = useState(false); // 登录/注册模式切换

  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [input, setInput] = useState('');
  const [isChatting, setIsChatting] = useState(false);

  const [projects, setProjects] = useState([]);
  const [currentProject, setCurrentProject] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [useNewProject, setUseNewProject] = useState(false);
  const fileInputRef = useRef(null);

  // --- 2. 初始化与监听 ---
  useEffect(() => {
    if (token) {
      fetchProjects();
      loadConversationHistory(token);
    }
  }, [token]);

  useEffect(() => {
    if (token && currentProject) {
      loadConversationHistory(token, currentProject);
    }
  }, [currentProject]);

  const fetchProjects = async () => {
    try {
      const res = await fetch(`${API_BASE}/projects`);
      const data = await res.json();
      if (data.status === "success" && data.projects) {
        // 🌟 核心修改：过滤掉“全部项目 (全局搜索)”
        const filtered = data.projects.filter(p => p !== "全部项目 (全局搜索)");
        setProjects(filtered);
        // 自动选中第一个有效项目
        if (filtered.length > 0 && !currentProject) {
          setCurrentProject(filtered[0]);
        }
      }
    } catch (err) {
      console.error("获取项目列表失败", err);
    }
  };

  // --- 3. 身份验证逻辑 ---
  const handleAuth = async (e) => {
    e.preventDefault();
    setIsLoggingIn(true);
    const endpoint = isRegisterMode ? '/register' : '/login';

    try {
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: loginUser, password: loginPwd })
      });
      const data = await res.json();
      
      if (res.ok) {
        if (isRegisterMode) {
          alert(`✅ 注册成功！请直接登录。`);
          setIsRegisterMode(false);
          setLoginPwd(''); 
        } else {
          setToken(data.token);
          setUsername(data.username);
          localStorage.setItem('token', data.token);
          localStorage.setItem('username', data.username);
          // 登录后加载最近会话的历史消息
          loadConversationHistory(data.token);
          setConversationId(null);
        }
      } else {
        alert(data.detail || (isRegisterMode ? '注册失败' : '登录失败，请检查账号密码'));
      }
    } catch (err) {
      alert('无法连接到服务器，请检查后端运行状态。');
    } finally {
      setIsLoggingIn(false);
    }
  };


  const deleteConversation = async (id) => {
    if (!confirm('确定删除这个会话？')) return;
    await fetch(`${API_BASE}/conversations/${id}?token=${token}`, { method: 'DELETE' });
    setConversations(prev => prev.filter(c => c.id !== id));
    if (conversationId === id) {
      setConversationId(null);
      setMessages([{ role: 'welcome', content: `Welcome! ${username}` }]);
    }
  };

  const newConversation = async () => {
    const name = prompt('对话名称：', currentProject || '新对话');
    if (!name) return;
    const res = await fetch(`${API_BASE}/conversations?token=${token}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: name, project_name: currentProject || null })
    });
    const data = await res.json();
    if (data.id) {
      setConversationId(data.id);
      setConversations(prev => [{ id: data.id, title: name, created_at: new Date().toISOString() }, ...prev]);
      setMessages([{ role: 'welcome', content: `Welcome! ${username}` }]);
    }
  };

  const handleLogout = () => {
    setToken('');
    setUsername('');
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    // 退出时：设置退出提示，确保下次进入不会残留之前的对话
    setMessages([{ role: 'bot', content: '已退出登录。期待下次见面！' }]);
  };


  const loadConversationHistory = async (authToken, forProject = '') => {
    try {
      const url = forProject ? `${API_BASE}/conversations?token=${authToken}&project_name=${encodeURIComponent(forProject)}` : `${API_BASE}/conversations?token=${authToken}`;
      const res = await fetch(url);
      const data = await res.json();
      if (data.conversations && data.conversations.length > 0) {
        setConversations(data.conversations);
        if (forProject) {
          const lastConv = data.conversations[0];
          setConversationId(lastConv.id);
          const histRes = await fetch(`${API_BASE}/conversations/${lastConv.id}?token=${authToken}`);
          const histData = await histRes.json();
          if (histData.history && histData.history.length > 0) {
            const msgs = [{ role: 'welcome', content: `Welcome! ${username}` }];
            for (const h of histData.history) {
              msgs.push({ role: h.role === 'assistant' ? 'bot' : h.role, content: h.content });
            }
            setMessages(msgs);
            return;
          }
        }
      }
      setMessages([{ role: 'welcome', content: `Welcome! ${username}` }]);
    } catch (e) {
      setMessages([{ role: 'welcome', content: `Welcome! ${username}` }]);
    }
  };

  // --- 4. 聊天与文件逻辑 ---
  const handleSend = async () => {
    if (!input.trim() || isChatting) return;
    
    const userMsg = input.trim();
    setInput('');
    
    // 发送第一条消息时，移除“Welcome”大字报
    const cleanMessages = messages.filter(m => m.role !== 'welcome');
    const newMessages = [...cleanMessages, { role: 'user', content: userMsg }];
    
    setMessages(newMessages);
    setIsChatting(true);

    try {
      // 提取对话历史 (FastAPI 接收的 [[u, b], ...] 格式)
      const history = [];
      for (let i = 0; i < cleanMessages.length; i++) {
        if (cleanMessages[i].role === 'user' && cleanMessages[i+1]?.role === 'bot') {
          history.push([cleanMessages[i].content, cleanMessages[i+1].content]);
        }
      }

      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg,
          history: history,
          project_name: currentProject, 
          top_k: 5,
          temperature: 0.1,
          token: token,
          conversation_id: conversationId
        })
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '请求失败');
      setMessages([...newMessages, { role: 'bot', content: data.answer }]);
      if (data.conversation_id) setConversationId(data.conversation_id);
    } catch (err) {
      setMessages([...newMessages, { role: 'bot', content: `⚠️ 出错了: ${err.message}` }]);
    } finally {
      setIsChatting(false);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const targetProject = useNewProject ? newProjectName.trim() : currentProject;
    if (!targetProject) {
      alert("请选择已有项目或输入新项目名称。");
      return;
    }

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('project_name', targetProject); 

    try {
      const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: formData });
      const data = await res.json();
      if (res.ok) {
        alert(`✅ ${data.message}`);
        if (useNewProject) { fetchProjects(); setNewProjectName(''); setUseNewProject(false); }
      } else alert(`❌ ${data.detail}`);
    } catch (err) {
      alert("⚠️ 文件上传失败。");
    } finally {
      setIsUploading(false);
      e.target.value = ''; 
    }
  };

  // --- 5. 视图：登录/注册页面 ---
  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-100 to-slate-200 p-4 font-sans">
        <div className="bg-white p-8 rounded-3xl shadow-2xl w-full max-w-md border border-slate-100 transform transition-all">
          <h2 className="text-4xl font-extrabold text-center text-slate-800 mb-2 mt-6 tracking-tight">智能问答系统（测试）</h2>
          <p className="text-center text-slate-500 mb-10 text-sm">
            {isRegisterMode ? '创建您的专属知识库账号' : '请登录以访问智能知识库系统'}
          </p>
          
          <form onSubmit={handleAuth} className="space-y-6">
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase ml-1 mb-2">用户名</label>
              <input type="text" required value={loginUser} onChange={e => setLoginUser(e.target.value)}
                className="w-full px-5 py-3 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                placeholder="请输入用户名" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase ml-1 mb-2">密码</label>
              <input type="password" required value={loginPwd} onChange={e => setLoginPwd(e.target.value)}
                className="w-full px-5 py-3 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                placeholder="请输入密码" />
            </div>
            <button type="submit" disabled={isLoggingIn}
              className="w-full bg-slate-900 hover:bg-black text-white font-bold py-4 rounded-xl transition-all flex justify-center items-center gap-2 shadow-lg">
              {isLoggingIn ? <Loader2 className="animate-spin" size={20} /> : (isRegisterMode ? <UserPlus size={20} /> : <Lock size={20} />)}
              {isLoggingIn ? '请稍候...' : (isRegisterMode ? '立即注册' : '开启系统')}
            </button>
          </form>

          <div className="mt-8 text-center text-sm text-slate-500">
            {isRegisterMode ? '已经有账号了？' : '首次使用该系统？'}
            <button type="button" onClick={() => setIsRegisterMode(!isRegisterMode)}
              className="text-blue-600 hover:underline font-bold ml-1">
              {isRegisterMode ? '直接登录' : '创建一个新账号'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // --- 6. 视图：主对话界面 ---
  return (
    <div className="flex h-screen bg-white overflow-hidden font-sans">
      
      {/* 侧边栏 */}
      <div className="w-72 bg-slate-900 text-slate-300 flex flex-col hidden md:flex shadow-inner">
        <div className="p-6 flex items-center gap-3 border-b border-slate-800">
          <Database className="text-blue-400" size={24} />
          <h1 className="text-xl font-black text-white tracking-tighter">智能问答系统（测试）</h1>
        </div>
        
        <div className="flex-1 p-6 space-y-8 overflow-y-auto">
          {/* 知识库列表 */}
          <div>
            <div className="flex items-center gap-2 text-xs font-bold text-slate-500 uppercase mb-4 tracking-widest">
              <FolderGit2 size={14} /> 知识库列表
            </div>
            <select 
              value={currentProject} 
              onChange={(e) => setCurrentProject(e.target.value)}
              className="w-full bg-slate-800 text-white border border-slate-700 rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-blue-500 outline-none cursor-pointer appearance-none shadow-sm"
            >
              {projects.length > 0 ? (
                projects.map(proj => <option key={proj} value={proj}>{proj}</option>)
              ) : (
                <option disabled>未加载知识库</option>
              )}
            </select>
          </div>

          <div className="border-t border-slate-800 pt-8">
{/* 会话列表 */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-500 uppercase tracking-widest">
                <MessageSquare size={14} /> 历史会话
              </div>
              <button onClick={newConversation} className="text-xs text-blue-400 hover:text-blue-300">+ 新建</button>
            </div>
            {conversations.length > 0 ? (
            <div className="max-h-40 overflow-y-auto space-y-1">
              {conversations.map(c => (
                <div key={c.id} onClick={async () => {
                    setConversationId(c.id);
                    const r = await fetch(`${API_BASE}/conversations/${c.id}?token=${token}`);
                    const d = await r.json();
                    const msgs = [{ role: 'welcome', content: `Welcome! ${username}` }];
                    (d.history || []).forEach(h => msgs.push({ role: h.role === 'assistant' ? 'bot' : h.role, content: h.content }));
                    setMessages(msgs);
                  }} className={`flex items-center justify-between px-3 py-2 rounded-lg text-xs cursor-pointer transition-all ${c.id === conversationId ? 'bg-blue-600/30 text-blue-200' : 'text-slate-400 hover:bg-slate-800'}`}>
                  <span className="truncate flex-1">{c.title}</span>
                  <button onClick={(e) => { e.stopPropagation(); deleteConversation(c.id); }} className="text-slate-600 hover:text-red-400 ml-1">&times;</button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-600">暂无会话</p>
          )}
          </div>

          <div className="border-t border-slate-800 pt-4">
             <div className="flex items-center gap-2 text-xs font-bold text-slate-500 uppercase mb-4 tracking-widest">
              <UploadCloud size={14} /> 知识入库
            </div>
            <div className="flex gap-1 mb-3">
              <button onClick={() => setUseNewProject(false)} className={"text-xs px-3 py-1 rounded-full transition-all " + (!useNewProject ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400')}>已有项目</button>
              <button onClick={() => setUseNewProject(true)} className={"text-xs px-3 py-1 rounded-full transition-all " + (useNewProject ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400')}>新建项目</button>
            </div>
            {useNewProject ? (
              <input type="text" value={newProjectName} onChange={e => setNewProjectName(e.target.value)} placeholder="输入新项目名称..." className="w-full mb-3 px-4 py-2 bg-slate-800 text-white rounded-xl text-sm outline-none border border-slate-700 focus:border-blue-500" />
            ) : (
              <p className="text-xs text-slate-500 mb-3">入库到：{currentProject || '未选择'}</p>
            )}
            <input type="file" ref={fileInputRef} onChange={handleFileUpload} className="hidden" accept=".txt,.pdf,.md,.docx" />
            <button 
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="w-full bg-white hover:bg-slate-100 text-slate-900 font-bold py-3 rounded-xl text-sm transition-all flex items-center justify-center gap-2 shadow-lg disabled:opacity-50"
            >
              {isUploading ? <Loader2 className="animate-spin" size={18} /> : <UploadCloud size={18} />}
              {isUploading ? '解析中...' : '选择文件上传'}
            </button>
          </div>
          </div>
        </div>

        {/* 用户信息 */}
        <div className="p-5 border-t border-slate-800 bg-slate-950/50 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-blue-600 text-white w-9 h-9 rounded-full flex items-center justify-center font-black text-sm shadow-inner">
              {username.charAt(0).toUpperCase()}
            </div>
            <span className="text-sm font-semibold text-slate-100">{username}</span>
          </div>
          <button onClick={handleLogout} className="text-slate-500 hover:text-red-400 p-2 rounded-lg hover:bg-slate-800 transition-all">
            <LogOut size={20} />
          </button>
        </div>
      </div>

      {/* 主对话区 */}
      <div className="flex-1 flex flex-col h-full bg-white relative">
        <div className="flex-1 overflow-y-auto p-6 md:p-12">
          <div className="max-w-3xl mx-auto w-full h-full">
            
            {/* 消息渲染列表 */}
            {messages.map((msg, idx) => {
              // 🌟 Gemini 风格欢迎页
              if (msg.role === 'welcome') {
                return (
                  <div key={idx} className="flex flex-col items-center justify-center h-full min-h-[50vh] text-center">
                    <div className="p-5 bg-blue-50 rounded-full mb-8 animate-pulse">
                       <Sparkles className="text-blue-600" size={56} />
                    </div>
                    <h2 className="text-6xl font-black bg-gradient-to-r from-blue-600 via-indigo-500 to-purple-600 bg-clip-text text-transparent mb-6 tracking-tighter">
                      {msg.content}
                    </h2>
                    <p className="text-slate-400 text-xl font-medium max-w-md">今天我该如何协助您的科研工作？请在下方提问。</p>
                  </div>
                );
              }
              
              // 普通气泡样式
              return (
                <div key={idx} className={`flex gap-5 mb-8 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                  <div className={`w-10 h-10 flex-shrink-0 rounded-xl flex items-center justify-center shadow-md ${msg.role === 'user' ? 'bg-slate-900 text-white' : 'bg-slate-100 text-blue-600'}`}>
                    {msg.role === 'user' ? <User size={20} /> : <Cpu size={20} />}
                  </div>
                  <div className={`px-5 py-4 rounded-2xl max-w-[85%] text-base leading-relaxed whitespace-pre-wrap shadow-sm border ${msg.role === 'user' ? 'bg-slate-900 text-white border-slate-900' : 'bg-slate-50 text-slate-800 border-slate-100'}`}>
                    {msg.content}
                  </div>
                </div>
              );
            })}
            
            {isChatting && (
               <div className="flex gap-5 mb-8">
                 <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-400"><Cpu size={20} /></div>
                 <div className="flex items-center gap-3 text-slate-400 font-medium italic">
                   <Loader2 className="animate-spin" size={16} /> 正在检索文档并生成回答...
                 </div>
               </div>
            )}
          </div>
        </div>

        {/* 输入框区域 */}
        <div className="p-8 bg-white">
          <div className="max-w-3xl mx-auto relative flex items-center shadow-2xl border border-slate-200 rounded-3xl bg-white focus-within:ring-4 focus-within:ring-blue-100 transition-all overflow-hidden">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if(e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder={`在 [ ${currentProject || '...'} ] 中提问...`}
              className="w-full py-5 pl-6 pr-20 outline-none resize-none max-h-40 text-lg text-slate-800 bg-white"
              rows="1"
            />
            <button 
              onClick={handleSend} 
              disabled={!input.trim() || isChatting}
              className="absolute right-4 bottom-3.5 w-12 h-12 bg-blue-600 text-white rounded-2xl flex items-center justify-center hover:bg-blue-700 disabled:bg-slate-200 disabled:text-slate-400 transition-all shadow-lg"
            >
              <Send size={22} />
            </button>
          </div>
          <p className="text-center text-xs text-slate-400 mt-4 font-medium uppercase tracking-widest">Powered by HUST</p>
        </div>
      </div>

    </div>
  );
}