import React, { useState, useEffect, useRef, useCallback } from 'react'
import AgentMapPanel from '../components/AgentMapPanel'
import './Agent.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
const SESSION_HISTORY_KEY = 'zrzy_session_history'

// ── 历史记录 ────────────────────────────────────────────────────────────────

function loadSessionHistory() {
  try {
    const raw = localStorage.getItem(SESSION_HISTORY_KEY)
    if (!raw) return []
    const list = JSON.parse(raw)
    return Array.isArray(list) ? list : []
  } catch { return [] }
}

function saveSessionHistory(list) {
  localStorage.setItem(SESSION_HISTORY_KEY, JSON.stringify(list.slice(0, 50)))
}

function upsertSessionHistory(list, session) {
  const firstUserMsg = session.messages?.find((m) => m.role === 'user')
  const title = firstUserMsg?.content?.slice(0, 40) || '新会话'
  const item = { id: session.id, title, state: session.state, created_at: session.created_at }
  const next = [item, ...list.filter((h) => h.id !== item.id)]
  saveSessionHistory(next)
  return next
}

// ── 侧边栏滚动条 ────────────────────────────────────────────────────────────

const SB = { trackInsetTop: 10, trackInsetBottom: 22, minThumb: 28, lengthScale: 0.5 }

function getScrollbarMetrics(el) {
  const { scrollTop, scrollHeight, clientHeight } = el
  const trackH = Math.max(clientHeight - SB.trackInsetTop - SB.trackInsetBottom, 0)
  if (scrollHeight <= clientHeight + 1 || trackH <= 0) return null
  const thumbH = Math.max((clientHeight / scrollHeight) * trackH * SB.lengthScale, SB.minThumb)
  const maxTop = Math.max(trackH - thumbH, 0)
  const thumbTop = (scrollTop / (scrollHeight - clientHeight)) * maxTop
  return { thumbH, thumbTop, maxTop, scrollRange: scrollHeight - clientHeight }
}

// ── 辅助函数 ────────────────────────────────────────────────────────────────

function sessionStatusClass(state) {
  if (state === 'DONE') return 'done'
  if (state === 'RUNNING') return 'running'
  if (state === 'ERROR') return 'failed'
  if (state === 'CONFIRM') return 'confirm'
  return 'active'
}

function stateLabel(state) {
  const map = {
    INTENT: '对话中', ASK_REGION: '对话中', ASK_YEAR: '对话中',
    ASK_MODEL: '对话中', CONFIRM: '待确认', RUNNING: '运行中',
    DONE: '已完成', ERROR: '出错', GREETING: '对话中',
  }
  return map[state] || state
}

// session 产物图片通过 /api/sessions/{id}/artifacts/{name} 访问
function sessionArtifactUrl(sessionId, name) {
  return `${API_BASE}/api/sessions/${sessionId}/artifacts/${encodeURIComponent(name)}`
}

// ── 轮询 Hook ────────────────────────────────────────────────────────────────
// state === 'RUNNING' 时每 2 秒拉取一次 session，直到 DONE/ERROR 才停止

function useSessionPoller(session, setSession, setHistory) {
  const pollRef = useRef(null)

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  useEffect(() => {
    if (session?.state !== 'RUNNING') {
      stopPoll()
      return
    }
    if (pollRef.current) return

    pollRef.current = setInterval(async () => {
      try {
        const resp = await fetch(`${API_BASE}/api/sessions/${session.id}`)
        if (!resp.ok) return
        const fresh = await resp.json()
        setSession(fresh)
        setHistory((prev) => upsertSessionHistory(prev, fresh))
        if (fresh.state !== 'RUNNING') stopPoll()
      } catch { /* 静默重试 */ }
    }, 2000)

    return stopPoll
  }, [session?.state, session?.id, stopPoll, setSession, setHistory])

  return stopPoll
}

// ── 消息渲染组件 ────────────────────────────────────────────────────────────

function ActionDoneMessage({ msg, sessionId }) {
  const images = msg.extra?.images?.filter(Boolean) || []
  const yearFromExtra = msg.extra?.year
  const yearFromText = msg.content?.match(/(20\d{2})/)?.[1]
  const year = yearFromExtra || yearFromText || ''
  const regionName = msg.extra?.region_name || ''
  const isInvestResult = Boolean(msg.extra?.invest_result)

  const parentCity = msg.extra?.parent_city || ''
  const fullRegion = `${parentCity}${regionName}`

  const getCaption = (name, idx) => {
    if (isInvestResult) {
      return `${year}年${fullRegion}${name.includes('carbon') ? '碳储量' : '生境质量'}模型输出结果`
    }
    return idx === 0
      ? `${year}年${fullRegion}土地利用数据裁剪结果`
      : `${year}年${fullRegion}土地利用数据重分类结果`
  }

  return (
    <div className="session-action-done">
      <span className="session-action-done-text">{msg.content}</span>
      {images.length > 0 && (
        <div className="session-action-images">
          {images.map((name, idx) => (
            <figure key={name} className="session-action-figure">
              <img src={sessionArtifactUrl(sessionId, name)} alt={name} loading="lazy" />
              <figcaption>{getCaption(name, idx)}</figcaption>
            </figure>
          ))}
        </div>
      )}
    </div>
  )
}

function ReportMessage({ msg }) {
  return <div className="chat-bubble chat-bubble--assistant">{msg.content}</div>
}

function RunningProgressBar() {
  return (
    <div className="session-running-bar">
      <div className="session-running-bar-track">
        <div className="session-running-bar-fill" />
      </div>
      <span className="session-running-bar-label">InVEST 模型运行中，请稍候…</span>
    </div>
  )
}

function ConfirmCard({ msg, onQuickReply, disabled }) {
  const { region, year, models } = msg.extra || {}
  const modelLabel = Array.isArray(models) && models.length > 0
    ? models.map((m) => m === 'habitat_quality' ? '生境质量' : m === 'carbon_storage' ? '碳储量' : m).join('、')
    : '未选择'
  return (
    <div className="session-confirm-card">
      <p className="session-confirm-card-title">请确认以下分析参数</p>
      <div className="session-confirm-card-params">
        {[['地区', region || '—'], ['年份', String(year || '—')], ['模型', modelLabel]].map(([label, value]) => (
          <div key={label} className="session-confirm-param">
            <span className="session-confirm-param-label">{label}</span>
            <span className="session-confirm-param-value">{value}</span>
          </div>
        ))}
      </div>
      <div className="session-confirm-card-actions">
        <button type="button" className="session-quick-btn session-quick-btn--primary" onClick={() => onQuickReply('确认')} disabled={disabled}>确认，开始运行</button>
        <button type="button" className="session-quick-btn session-quick-btn--secondary" onClick={() => onQuickReply('重新填写')} disabled={disabled}>重新填写</button>
      </div>
    </div>
  )
}

function ConfigDownloadMessage({ msg, sessionId }) {
  const text = msg.content.replace(/[：:]\s*session_config\.json[。.]?/g, '').trim()
  return (
    <div className="session-config-download">
      <span className="session-config-text">{text}</span>
      <a href={`${API_BASE}/api/sessions/${sessionId}/config`} target="_blank" rel="noreferrer" className="session-config-link" download="session_config.json">session_config.json</a>
    </div>
  )
}

function ModelQuickReplyBar({ onQuickReply, disabled }) {
  return (
    <div className="session-quick-reply-bar">
      {[['生境质量', '生境质量'], ['碳储量', '碳储量'], ['两个都要', '两个都要']].map(([label, value]) => (
        <button key={value} type="button" className="session-quick-btn" onClick={() => onQuickReply(value)} disabled={disabled}>{label}</button>
      ))}
    </div>
  )
}

function MessageBubble({ msg, sessionId, onQuickReply, disabled }) {
  if (msg.role === 'user') return (
    <div className="chat-message chat-message--user">
      <div className="chat-bubble chat-bubble--user">{msg.content}</div>
    </div>
  )
  if (msg.type === 'confirm_card') return (
    <div className="chat-message chat-message--assistant">
      <ConfirmCard msg={msg} onQuickReply={onQuickReply} disabled={disabled} />
    </div>
  )
  if (msg.type === 'config_download') return (
    <div className="chat-message chat-message--assistant">
      <div className="chat-bubble chat-bubble--assistant">
        <ConfigDownloadMessage msg={msg} sessionId={sessionId} />
      </div>
    </div>
  )
  if (msg.type === 'action_done') return (
    <div className="chat-message chat-message--assistant">
      <div className="chat-bubble chat-bubble--assistant">
        <ActionDoneMessage msg={msg} sessionId={sessionId} />
      </div>
    </div>
  )
  if (msg.type === 'report') return (
    <div className="chat-message chat-message--assistant">
      <ReportMessage msg={msg} />
    </div>
  )
  if (msg.type === 'action_progress') return (
    <div className="chat-message chat-message--assistant">
      <div className="chat-bubble chat-bubble--assistant chat-bubble--progress">
        {msg.content}
      </div>
    </div>
  )
  return (
    <div className="chat-message chat-message--assistant">
      <div className="chat-bubble chat-bubble--assistant">{msg.content}</div>
    </div>
  )
}

function SessionThread({ session, sending, onQuickReply }) {
  const messages = session?.messages || []
  const state = session?.state
  const isRunning = state === 'RUNNING'
  return (
    <div className="agent-chat-thread">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} msg={msg} sessionId={session?.id} onQuickReply={onQuickReply} disabled={sending || isRunning} />
      ))}
      {isRunning && <RunningProgressBar />}
      {sending && !isRunning && (
        <div className="chat-message chat-message--assistant">
          <div className="chat-bubble chat-bubble--assistant chat-bubble--thinking">
            <span className="thinking-dot" /><span className="thinking-dot" /><span className="thinking-dot" />
          </div>
        </div>
      )}
    </div>
  )
}

// ── 图标 ────────────────────────────────────────────────────────────────────

function IconSearch() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
      <path d="M20 20L16 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}
function IconSidebar() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="2" />
      <path d="M9 4V20" stroke="currentColor" strokeWidth="2" />
    </svg>
  )
}
function IconSend() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 4v13M12 4l-6 6M12 4l6 6" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ── Agent 主组件 ────────────────────────────────────────────────────────────

export default function Agent() {
  const [input, setInput] = useState('')
  const [session, setSession] = useState(null)
  const [sending, setSending] = useState(false)
  const [apiError, setApiError] = useState('')
  const [history, setHistory] = useState(loadSessionHistory)
  const [activeId, setActiveId] = useState(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [historyThumb, setHistoryThumb] = useState({ top: 0, height: 0, show: false })

  const scrollRef = useRef(null)
  const searchInputRef = useRef(null)
  const historyListRef = useRef(null)
  const dragRef = useRef({ active: false, startY: 0, startScrollTop: 0, maxTop: 0, scrollRange: 0 })

  const chatActive = Boolean(session)
  const isRunning = session?.state === 'RUNNING'

  // RUNNING 状态时自动轮询，直到 DONE / ERROR
  useSessionPoller(session, setSession, setHistory)

  // API -----------------------------------------------------------------------

  const createSession = useCallback(async (prefill = null) => {
    setSending(true)
    setApiError('')
    try {
      const resp = await fetch(`${API_BASE}/api/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prefill }),
      })
      if (!resp.ok) throw new Error()
      const data = await resp.json()
      setSession(data)
      setActiveId(data.id)
      setHistory((prev) => upsertSessionHistory(prev, data))
      return data
    } catch {
      setApiError('无法连接后端，请确认 uvicorn 已启动。')
      return null
    } finally {
      setSending(false)
    }
  }, [])

  const sendMessage = useCallback(async (text) => {
    if (!session || !text.trim() || sending || isRunning) return
    setSending(true)
    setApiError('')
    const optimisticMsg = { id: crypto.randomUUID(), role: 'user', type: 'text', content: text, extra: {} }
    setSession((prev) => prev ? { ...prev, messages: [...prev.messages, optimisticMsg] } : prev)
    try {
      const resp = await fetch(`${API_BASE}/api/sessions/${session.id}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (!resp.ok) throw new Error()
      const freshResp = await fetch(`${API_BASE}/api/sessions/${session.id}`)
      if (freshResp.ok) {
        const freshSession = await freshResp.json()
        setSession(freshSession)
        setHistory((prev) => upsertSessionHistory(prev, freshSession))
      }
    } catch {
      setSession((prev) => prev
        ? { ...prev, messages: prev.messages.filter((m) => m.id !== optimisticMsg.id) }
        : prev)
      setApiError('发送失败，请检查网络连接。')
    } finally {
      setSending(false)
    }
  }, [session, sending, isRunning])

  const fetchSession = useCallback(async (id) => {
    try {
      const resp = await fetch(`${API_BASE}/api/sessions/${id}`)
      if (!resp.ok) throw new Error()
      return await resp.json()
    } catch { return null }
  }, [])

  // 交互 -----------------------------------------------------------------------

  const handleSend = async () => {
    const text = input.trim()
    if (!text || sending || isRunning) return
    setInput('')
    await sendMessage(text)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!sending && !isRunning && input.trim()) handleSend()
    }
  }

  const handleQuickReply = useCallback(async (text) => {
    setInput('')
    await sendMessage(text)
  }, [sendMessage])

  const handleNewChat = async () => {
    setActiveId(null)
    setSession(null)
    setInput('')
    setApiError('')
    await createSession()
  }

  const selectHistory = useCallback(async (item) => {
    setApiError('')
    setActiveId(item.id)
    const data = await fetchSession(item.id)
    if (data) {
      setSession(data)
    } else {
      setApiError('无法加载该会话，后端可能已重启或会话已被清理。')
      setSession(null)
      setActiveId(null)
    }
  }, [fetchSession])

  // 副作用 ---------------------------------------------------------------------

  useEffect(() => {
    const pendingId = sessionStorage.getItem('pending_session_id')
    if (pendingId) {
      sessionStorage.removeItem('pending_session_id')
      fetchSession(pendingId).then((data) => {
        if (data) { setSession(data); setActiveId(data.id); setHistory((prev) => upsertSessionHistory(prev, data)) }
      })
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [session?.messages?.length, sending, isRunning])

  useEffect(() => {
    if (searchOpen && searchInputRef.current) searchInputRef.current.focus()
  }, [searchOpen])

  // 侧边栏滚动条 ---------------------------------------------------------------

  const updateScrollbar = useCallback(() => {
    const el = historyListRef.current
    if (!el) return
    const m = getScrollbarMetrics(el)
    if (!m) { setHistoryThumb({ top: 0, height: 0, show: false }); return }
    setHistoryThumb({ top: m.thumbTop, height: m.thumbH, show: true })
  }, [])

  const handleThumbDown = useCallback((event) => {
    event.preventDefault()
    event.stopPropagation()
    const el = historyListRef.current
    const m = el ? getScrollbarMetrics(el) : null
    if (!el || !m) return
    dragRef.current = { active: true, startY: event.clientY, startScrollTop: el.scrollTop, maxTop: m.maxTop, scrollRange: m.scrollRange }
    const onMove = (e) => {
      if (!dragRef.current.active) return
      const delta = e.clientY - dragRef.current.startY
      el.scrollTop = dragRef.current.startScrollTop + (dragRef.current.maxTop ? (delta / dragRef.current.maxTop) * dragRef.current.scrollRange : 0)
    }
    const onUp = () => {
      dragRef.current.active = false
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
  }, [])

  const handleTrackDown = useCallback((event) => {
    if (event.target.classList.contains('agent-history-scrollbar-thumb')) return
    const el = historyListRef.current
    const m = el ? getScrollbarMetrics(el) : null
    if (!el || !m) return
    const rect = event.currentTarget.getBoundingClientRect()
    const ratio = m.maxTop > 0 ? Math.min(Math.max((event.clientY - rect.top - m.thumbH / 2) / m.maxTop, 0), 1) : 0
    el.scrollTop = ratio * m.scrollRange
  }, [])

  useEffect(() => {
    updateScrollbar()
    const el = historyListRef.current
    if (!el) return
    const observer = new ResizeObserver(updateScrollbar)
    observer.observe(el)
    window.addEventListener('resize', updateScrollbar)
    return () => { observer.disconnect(); window.removeEventListener('resize', updateScrollbar) }
  }, [history.length, updateScrollbar])

  const filteredHistory = searchQuery.trim()
    ? history.filter((h) => h.title?.toLowerCase().includes(searchQuery.trim().toLowerCase()))
    : history

  // 渲染 -----------------------------------------------------------------------

  return (
    <div className="agent">
      <aside className={`agent-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <header className="agent-sidebar-header">
          <div className="agent-sidebar-brand">自然资源调查数据智能化分析</div>
          <div className="agent-sidebar-actions">
            <button type="button" className={`agent-icon-btn ${searchOpen ? 'active' : ''}`}
              onClick={() => setSearchOpen((o) => { if (o) setSearchQuery(''); return !o })}
              title="搜索历史" aria-label="搜索历史"><IconSearch /></button>
            <button type="button" className="agent-icon-btn" onClick={() => setSidebarCollapsed(true)} title="收起侧边栏" aria-label="收起侧边栏"><IconSidebar /></button>
          </div>
        </header>

        {searchOpen && (
          <div className="agent-search-wrap">
            <input ref={searchInputRef} type="search" className="agent-search-input" placeholder="搜索历史会话…" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
          </div>
        )}

        <button type="button" className="agent-new-btn" onClick={handleNewChat}>
          <span className="agent-new-icon">+</span>新建会话
        </button>

        <div className="agent-history-panel">
          <div className="agent-history-scroll-wrap">
            <div ref={historyListRef} className="agent-history-list" onScroll={updateScrollbar}>
              {filteredHistory.length === 0
                ? <p className="agent-history-empty">{searchQuery ? '未找到匹配的会话' : '暂无历史会话'}</p>
                : filteredHistory.map((item) => (
                  <button key={item.id} type="button"
                    className={`agent-history-item status-${sessionStatusClass(item.state)} ${activeId === item.id ? 'active' : ''}`}
                    onClick={() => selectHistory(item)} title={item.title}>
                    <span className="agent-history-text">{item.title}</span>
                    <span className={`agent-history-state-dot state-${sessionStatusClass(item.state)}`} title={stateLabel(item.state)} />
                  </button>
                ))
              }
            </div>
            {historyThumb.show && (
              <div className="agent-history-scrollbar" aria-hidden="true" onPointerDown={handleTrackDown}>
                <div className="agent-history-scrollbar-thumb"
                  style={{ height: `${historyThumb.height}px`, transform: `translateY(${historyThumb.top}px)` }}
                  onPointerDown={handleThumbDown} />
              </div>
            )}
          </div>
        </div>
      </aside>

      {sidebarCollapsed && (
        <button type="button" className="agent-sidebar-reopen" onClick={() => setSidebarCollapsed(false)} title="展开侧边栏" aria-label="展开侧边栏"><IconSidebar /></button>
      )}

      <div className={`agent-workspace with-map ${sidebarCollapsed ? 'expanded' : ''}`}>
        <main className="agent-main with-map">
          <div className="agent-main-scroll" ref={scrollRef}>
            {!chatActive && (
              <div className="agent-welcome">
                <h1 className="agent-welcome-title">你好，我是自然资源调查数据智能化分析助手</h1>
                <button
                  type="button"
                  className="agent-welcome-start-btn"
                  onClick={() => createSession()}
                  disabled={sending}
                >
                  {sending ? '初始化中…' : '立即开始'}
                </button>
                {apiError && <p className="session-api-error">{apiError}</p>}
              </div>
            )}
            {chatActive && (
              <SessionThread session={session} sending={sending} onQuickReply={handleQuickReply} />
            )}
          </div>

          {chatActive && (
            <footer className="agent-input-bar agent-input-bar--dock">
              {apiError && <p className="session-api-error">{apiError}</p>}
              <div className="agent-input-box">
                <textarea rows={1}
                  placeholder={isRunning ? 'InVEST 运行中，请稍候…' : '请输入您的回复…'}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={sending || isRunning}
                  aria-label="输入消息"
                />
                <button type="button" className="agent-submit-btn"
                  onClick={handleSend}
                  disabled={sending || isRunning || !input.trim()}
                  title="发送" aria-label="发送">
                  {sending ? '…' : <IconSend />}
                </button>
              </div>
            </footer>
          )}
        </main>
        <AgentMapPanel session={session} />
      </div>
    </div>
  )
}

// 供技术方案页"运行模型"按钮调用
export async function startSessionWithPrefill(prefill) {
  const resp = await fetch(`${API_BASE}/api/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prefill }),
  })
  if (!resp.ok) throw new Error('创建会话失败')
  const data = await resp.json()
  sessionStorage.setItem('pending_session_id', data.id)
  return data
}
