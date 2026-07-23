import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Link, useParams, Navigate } from 'react-router-dom'
import Map, { Marker, Source, Layer } from 'react-map-gl/mapbox'
import 'mapbox-gl/dist/mapbox-gl.css'
import { getModuleById } from '../data/investModules'
import { AGENT_MAP_STYLE, applyAgentBlueTheme } from '../lib/agentMapTheme'
import './SolutionDetail.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''
const ANJI_VIEW_STATE = { longitude: 119.68, latitude: 30.63, zoom: 8.7 }
const CATEGORY_PATHS = {
  terrestrial: ['面向应用的分类', '自然视角', '陆地生态系统'],
  freshwater: ['面向应用的分类', '自然视角', '淡水生态系统'],
  marine: ['面向应用的分类', '自然视角', '海洋与海岸带'],
  urban: ['面向应用的分类', '人居环境视角', '城市生态系统'],
  supporting: ['面向应用的分类', '模型支撑能力', '辅助与支撑工具'],
}

const WORKFLOW_STEPS = [
  ['params', '参数配置', '确认模型、研究区和数据年份'],
  ['data', '数据匹配', '匹配土地利用、边界和模型参数表'],
  ['clip', '行政区裁剪', '按研究区边界裁剪土地利用栅格'],
  ['reclass', '土地利用重分类', '生成 InVEST 模型所需的重分类栅格'],
  ['invest', 'InVEST 模型运行', '调用 InVEST 完成生态系统服务计算'],
  ['result', '成果制图与汇总', '生成专题图、统计结果和可下载配置'],
]

function useSessionPoller(session, setSession) {
  const pollRef = useRef(null)

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  useEffect(() => {
    if (session?.state !== 'RUNNING') { stopPoll(); return }
    if (pollRef.current) return
    pollRef.current = setInterval(async () => {
      try {
        const resp = await fetch(`${API_BASE}/api/sessions/${session.id}`)
        if (!resp.ok) return
        const fresh = await resp.json()
        setSession(fresh)
        if (fresh.state !== 'RUNNING') stopPoll()
      } catch { /* 静默重试 */ }
    }, 2000)
    return stopPoll
  }, [session?.state, session?.id, stopPoll, setSession])
}

function sessionArtifactUrl(sessionId, name) {
  return `${API_BASE}/api/sessions/${sessionId}/artifacts/${encodeURIComponent(name)}`
}

function RunningProgressBar() {
  return (
    <div className="sd-running-bar">
      <div className="sd-running-bar-track">
        <div className="sd-running-bar-fill" />
      </div>
      <span className="sd-running-bar-label">InVEST 模型运行中，请稍候…</span>
    </div>
  )
}

function ActionDoneMessage({ msg, sessionId }) {
  const images = msg.extra?.images?.filter(Boolean) || []
  const year = msg.extra?.year || msg.content?.match(/(20\d{2})/)?.[1] || ''
  const regionName = msg.extra?.region_name || '安吉县'
  const isInvestResult = Boolean(msg.extra?.invest_result)
  const getCaption = (name, idx) => {
    if (isInvestResult) {
      return `${year}年${regionName}${name.includes('carbon') ? '碳储量' : '生境质量'}模型输出结果`
    }
    return idx === 0
      ? `${year}年${regionName}土地利用数据裁剪结果`
      : `${year}年${regionName}土地利用数据重分类结果`
  }
  return (
    <div className="sd-action-done">
      <span className="sd-action-done-text">{msg.content}</span>
      {images.length > 0 && (
        <div className="sd-action-images">
          {images.map((name, idx) => (
            <figure key={name} className="sd-action-figure">
              <img src={sessionArtifactUrl(sessionId, name)} alt={name} loading="lazy" />
              <figcaption>{getCaption(name, idx)}</figcaption>
            </figure>
          ))}
        </div>
      )}
    </div>
  )
}

function ConfirmCard({ msg, onQuickReply, disabled }) {
  const { region, year, models } = msg.extra || {}
  const modelLabel = Array.isArray(models) && models.length > 0
    ? models.map((m) => m === 'habitat_quality' ? '生境质量' : m === 'carbon_storage' ? '碳储量' : m).join('、')
    : '未选择'
  return (
    <div className="sd-confirm-card">
      <p className="sd-confirm-card-title">请确认以下分析参数</p>
      <div className="sd-confirm-card-params">
        {[['地区', region || '—'], ['年份', String(year || '—')], ['模型', modelLabel]].map(([label, value]) => (
          <div key={label} className="sd-confirm-param">
            <span className="sd-confirm-param-label">{label}</span>
            <span className="sd-confirm-param-value">{value}</span>
          </div>
        ))}
      </div>
      <div className="sd-confirm-card-actions">
        <button type="button" className="sd-quick-btn sd-quick-btn--primary" onClick={() => onQuickReply('确认')} disabled={disabled}>确认，开始运行</button>
        <button type="button" className="sd-quick-btn sd-quick-btn--secondary" onClick={() => onQuickReply('重新填写')} disabled={disabled}>重新填写</button>
      </div>
    </div>
  )
}

function ConfigDownloadMessage({ msg, sessionId }) {
  const text = msg.content.replace(/[：:]\s*session_config\.json[。.]?/g, '').trim()
  return (
    <div className="sd-config-download">
      <span className="sd-config-text">{text}</span>
      <a href={`${API_BASE}/api/sessions/${sessionId}/config`} target="_blank" rel="noreferrer" className="sd-config-link" download="session_config.json">session_config.json</a>
    </div>
  )
}

function MessageBubble({ msg, sessionId, onQuickReply, disabled }) {
  if (msg.role === 'user') return (
    <div className="sd-chat-message sd-chat-message--user">
      <div className="sd-chat-bubble sd-chat-bubble--user">{msg.content}</div>
    </div>
  )
  if (msg.type === 'confirm_card') return (
    <div className="sd-chat-message sd-chat-message--assistant">
      <ConfirmCard msg={msg} onQuickReply={onQuickReply} disabled={disabled} />
    </div>
  )
  if (msg.type === 'config_download') return (
    <div className="sd-chat-message sd-chat-message--assistant">
      <div className="sd-chat-bubble sd-chat-bubble--assistant">
        <ConfigDownloadMessage msg={msg} sessionId={sessionId} />
      </div>
    </div>
  )
  if (msg.type === 'action_done') return (
    <div className="sd-chat-message sd-chat-message--assistant">
      <div className="sd-chat-bubble sd-chat-bubble--assistant">
        <ActionDoneMessage msg={msg} sessionId={sessionId} />
      </div>
    </div>
  )
  if (msg.type === 'action_progress') return (
    <div className="sd-chat-message sd-chat-message--assistant">
      <div className="sd-chat-bubble sd-chat-bubble--assistant sd-chat-bubble--progress">{msg.content}</div>
    </div>
  )
  return (
    <div className="sd-chat-message sd-chat-message--assistant">
      <div className="sd-chat-bubble sd-chat-bubble--assistant">{msg.content}</div>
    </div>
  )
}

function getWorkflowStatus(session, sending) {
  if (session?.state === 'ERROR') return ['error', '运行失败']
  if (session?.state === 'DONE') return ['done', '已完成']
  if (session?.state === 'RUNNING' || sending) return ['running', '运行中']
  return ['idle', '']
}

function getWorkflowStepStatus(stepId, session, sending) {
  const messages = session?.messages || []
  const hasDataResult = messages.some((msg) => msg.type === 'action_done' && msg.extra?.images?.length && !msg.extra?.invest_result)
  const hasInvestResult = messages.some((msg) => msg.type === 'action_done' && msg.extra?.invest_result)

  if (session?.state === 'ERROR' && ['invest', 'result'].includes(stepId)) return 'error'
  if (stepId === 'params') return session || sending ? 'done' : 'pending'
  if (stepId === 'data') return hasDataResult ? 'done' : (session || sending ? 'running' : 'pending')
  if (['clip', 'reclass'].includes(stepId)) return hasDataResult ? 'done' : 'pending'
  if (stepId === 'invest') {
    if (hasInvestResult || session?.state === 'DONE') return 'done'
    if (session?.state === 'RUNNING') return 'running'
    return hasDataResult ? 'pending' : 'pending'
  }
  if (stepId === 'result') return session?.state === 'DONE' ? 'done' : session?.state === 'RUNNING' ? 'pending' : 'pending'
  return 'pending'
}

function getResultImages(session) {
  return (session?.messages || []).flatMap((msg) => {
    const images = msg.extra?.images?.filter(Boolean) || []
    const year = msg.extra?.year || msg.content?.match(/(20\d{2})/)?.[1] || ''
    const regionName = msg.extra?.region_name || '安吉县'
    const isInvestResult = Boolean(msg.extra?.invest_result)
    return images.map((name, idx) => ({
      name,
      caption: isInvestResult
        ? `${year}年${regionName}${name.includes('carbon') ? '碳储量' : '生境质量'}模型输出结果`
        : idx === 0
          ? `${year}年${regionName}土地利用数据裁剪结果`
          : `${year}年${regionName}土地利用数据重分类结果`,
    }))
  })
}

function MiniMapboxPanel({ selectedRegion, session }) {
  const mapRef = useRef(null)
  const [viewState, setViewState] = useState({ longitude: 119.68, latitude: 30.63, zoom: 9 })
  const [overlayLayer, setOverlayLayer] = useState(null)

  const sessionId = session?.id
  const sessionState = session?.state
  const planYear = session?.plan?.year
  const regionCode = session?.plan?.region_code
  const models = session?.plan?.models || []

  useEffect(() => {
    if (!sessionId || sessionState !== 'DONE' || !planYear) {
      setOverlayLayer(null)
      return
    }

    const artifact = models.includes('carbon_storage')
      ? `carbon_storage_${planYear}_overlay.png`
      : `habitat_quality_${planYear}_overlay.png`

    let cancelled = false
    fetch(`${API_BASE}/api/sessions/${sessionId}/artifacts/${encodeURIComponent(artifact)}/bounds`)
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then((meta) => {
        if (cancelled) return
        setOverlayLayer({
          url: `${API_BASE}/api/sessions/${sessionId}/artifacts/${encodeURIComponent(artifact)}`,
          coordinates: meta.coordinates,
        })
        const map = mapRef.current
        if (map && meta.bounds?.length === 4) {
          map.fitBounds(
            [[meta.bounds[0], meta.bounds[1]], [meta.bounds[2], meta.bounds[3]]],
            { padding: 40, duration: 800 },
          )
        }
      })
      .catch(() => { if (!cancelled) setOverlayLayer(null) })

    return () => { cancelled = true }
  }, [sessionId, sessionState, planYear])

  useEffect(() => {
    if (!regionCode || !mapRef.current) return
    fetch(`${API_BASE}/api/regions/${regionCode}/boundary`)
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then((data) => {
        const map = mapRef.current
        if (map && data.bounds?.length === 4 && !overlayLayer) {
          map.fitBounds(
            [[data.bounds[0], data.bounds[1]], [data.bounds[2], data.bounds[3]]],
            { padding: 48, duration: 800 },
          )
        }
      })
      .catch(() => {})
  }, [regionCode])

  const onMapLoad = useCallback((evt) => {
    mapRef.current = evt.target
    applyAgentBlueTheme(evt.target)
  }, [])

  if (!MAPBOX_TOKEN) {
    return (
      <section className="sd-section sd-mini-map-section">
        <h2 className="sd-section-title">研究区位置</h2>
        <div className="sd-mini-map-fallback">未配置 Mapbox Token，暂无法显示地图。</div>
      </section>
    )
  }

  return (
    <section className="sd-section sd-mini-map-section">
      <h2 className="sd-section-title">研究区位置</h2>
      <div className="sd-mini-map">
        <Map
          mapboxAccessToken={MAPBOX_TOKEN}
          mapStyle={AGENT_MAP_STYLE}
          {...viewState}
          onMove={(evt) => setViewState(evt.viewState)}
          onLoad={onMapLoad}
          attributionControl={false}
          dragRotate={false}
          touchPitch={false}
          style={{ width: '100%', height: '100%' }}
        >
          {!overlayLayer && (
            <Marker longitude={119.68} latitude={30.63} anchor="bottom">
              <div className="sd-mini-map-marker" />
            </Marker>
          )}
          {overlayLayer && (
            <Source
              id="result-overlay"
              type="image"
              url={overlayLayer.url}
              coordinates={overlayLayer.coordinates}
            >
              <Layer
                id="result-overlay-layer"
                type="raster"
                paint={{ 'raster-opacity': 0.92 }}
              />
            </Source>
          )}
        </Map>
        <div className="sd-mini-map-label">
          <strong>{selectedRegion || '安吉县'}</strong>
          <span>浙江省湖州市</span>
        </div>
      </div>
    </section>
  )
}

function ResultPanel({ session, sending, apiError, selectedRegion, selectedYear, module }) {
  const [stateClass, stateText] = getWorkflowStatus(session, sending)
  const images = getResultImages(session)
  const modelName = module?.id === 'carbon_storage' ? '碳储量' : '生境质量'

  return (
    <div className="sd-result-panel sd-workflow-panel">
      <div className="sd-result-panel-header sd-workflow-panel-header">
        <div>
          <span className="sd-result-panel-title">分析流程</span>
          <p className="sd-workflow-panel-subtitle">按预设步骤完成数据处理、模型计算与成果整理</p>
        </div>
        <span className={`sd-result-state-badge sd-result-state-badge--${stateClass}`}>
          {stateText && stateText}
        </span>
      </div>
      {apiError && <p className="sd-api-error">{apiError}</p>}
      <div className="sd-workflow-summary">
        <div><span>模型</span><strong>{modelName}</strong></div>
        <div><span>地区</span><strong>{selectedRegion || '未选择'}</strong></div>
        <div><span>年份</span><strong>{selectedYear || '未选择'}</strong></div>
      </div>
      <div className="sd-result-scroll">
        <div className="sd-workflow-list">
          {WORKFLOW_STEPS.map(([id, title, desc], idx) => {
            const status = getWorkflowStepStatus(id, session, sending)
            return (
              <div key={id} className={`sd-workflow-item sd-workflow-item--${status}`}>
                <div className="sd-workflow-index">
                  {status === 'done' ? '✓' : idx + 1}
                </div>
                <div className="sd-workflow-body">
                  <div className="sd-workflow-title-row">
                    <h3>{title}</h3>
                    <span className="sd-workflow-status">
                      {status === 'running' && <i className="sd-wait-spinner" aria-hidden="true" />}
                      {status === 'done' ? '已完成' : status === 'running' ? '运行中' : status === 'error' ? '失败' : null}
                    </span>
                  </div>
                  <p>{desc}</p>
                </div>
              </div>
            )
          })}
        </div>

        <section className="sd-workflow-results">
          <div className="sd-workflow-results-head">
            <h3>成果展示</h3>
            <span>{images.length} 个成果图</span>
          </div>
          {images.length === 0 ? (
            <p className="sd-workflow-empty">工作流启动后，裁剪图、重分类图和模型输出图将在这里自动汇总。</p>
          ) : (
            <div className="sd-action-images">
              {images.map((image) => (
                <figure key={image.name} className="sd-action-figure">
                  <img src={sessionArtifactUrl(session.id, image.name)} alt={image.caption} loading="lazy" />
                  <figcaption>{image.caption}</figcaption>
                </figure>
              ))}
            </div>
          )}
          {session?.state === 'DONE' && (
            <a href={`${API_BASE}/api/sessions/${session.id}/config`} target="_blank" rel="noreferrer" className="sd-config-link sd-config-link--workflow" download="session_config.json">下载运行配置</a>
          )}
        </section>
      </div>
    </div>
  )
}

function SolutionDetail() {
  const { moduleId } = useParams()
  const module = getModuleById(moduleId)

  const [selectedRegion, setSelectedRegion] = useState('')
  const [selectedYear, setSelectedYear] = useState('')
  const [session, setSession] = useState(null)
  const [sending, setSending] = useState(false)
  const [apiError, setApiError] = useState('')

  useSessionPoller(session, setSession)
  const isRunning = session?.state === 'RUNNING'

  useEffect(() => {
    if (module?.supportedRegions?.length > 0) setSelectedRegion(module.supportedRegions[0])
    if (module?.supportedYears?.length > 0) setSelectedYear(String(module.supportedYears[module.supportedYears.length - 1]))
  }, [module])

  const handleResetWorkflow = useCallback(() => {
    setSession(null)
    setSending(false)
    setApiError('')
  }, [])

  const handleRunModel = useCallback(async () => {
    if (!selectedRegion || !selectedYear || isRunning || sending) return
    setSending(true)
    setApiError('')
    try {
      const modelId = module?.id === 'carbon_storage' ? 'carbon_storage' : 'habitat_quality'
      const createResp = await fetch(`${API_BASE}/api/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prefill: { models: [modelId] } }),
      })
      if (!createResp.ok) {
        const detail = await createResp.text()
        throw new Error(detail || '创建会话失败')
      }

      let currentSession = await createResp.json()
      setSession(currentSession)

      const sendStep = async (text) => {
        const resp = await fetch(`${API_BASE}/api/sessions/${currentSession.id}/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text }),
        })
        if (!resp.ok) {
          const detail = await resp.text()
          throw new Error(detail || '发送参数失败')
        }
        const freshResp = await fetch(`${API_BASE}/api/sessions/${currentSession.id}`)
        if (!freshResp.ok) throw new Error('无法获取会话状态')
        currentSession = await freshResp.json()
        setSession(currentSession)
        return currentSession
      }

      await sendStep(selectedRegion)
      await sendStep(String(selectedYear))
      await sendStep('确认')
    } catch (error) {
      setApiError(error instanceof Error ? error.message : '工作流运行失败，请检查后端服务。')
    } finally {
      setSending(false)
    }
  }, [isRunning, sending, selectedRegion, selectedYear, module])

  if (!module) return <Navigate to="/solutions" replace />
  if (module.status !== 'available') return <Navigate to="/solutions" replace />

  const canRun = selectedRegion && selectedYear && !isRunning && !sending

  return (
    <div className="solution-detail-page">
      <nav className="solution-breadcrumb">
        <Link to="/solutions">技术方案</Link>
        <span className="solution-breadcrumb-sep">/</span>
        <span>{module.name}</span>
      </nav>

      <div className="sd-two-col-layout">
        <aside className="sd-left-panel">
          <header className="sd-left-header">
            <div className="sd-title-row">
              <h1 className="sd-title">{module.name}</h1>
              <span className="sd-title-en">{module.nameEn}</span>
            </div>
            <p className="sd-summary">{module.summary}</p>
            <div className="sd-tags">
              {module.tags.map((tag) => (
                <span key={tag} className="sd-tag">{tag}</span>
              ))}
            </div>
          </header>

          <section className="sd-section">
            <h2 className="sd-section-title">分类</h2>
            <div className="sd-category-path" aria-label="模块分类">
              {(CATEGORY_PATHS[module.category] || ['面向应用的分类', '自然视角', module.category]).map((item, index, arr) => (
                <React.Fragment key={`${item}-${index}`}>
                  <span className={index === arr.length - 1 ? 'sd-category-path-current' : ''}>{item}</span>
                  {index < arr.length - 1 && <span className="sd-category-path-sep">›</span>}
                </React.Fragment>
              ))}
            </div>
          </section>

          <section className="sd-section">
            <h2 className="sd-section-title">详细说明</h2>
            <p className="sd-section-content sd-section-content--long">{module.description}</p>
          </section>

          <section className="sd-section">
            <h2 className="sd-section-title">所需数据</h2>
            <ul className="sd-data-list">
              {module.dataRequirements.map((item) => (<li key={item}>{item}</li>))}
            </ul>
          </section>


          <section className="sd-action-section">
            <h2 className="sd-section-title">模型运行</h2>
            <div className="sd-action-inline-row sd-action-inline-row--compact">
              <label className="sd-form-label">
                地区
                <select className="sd-form-select" value={selectedRegion}
                  onChange={(e) => { setSelectedRegion(e.target.value); handleResetWorkflow() }}
                  disabled={isRunning || sending}>
                  {module.supportedRegions.map((r) => (<option key={r} value={r}>{r}</option>))}
                </select>
              </label>
              <label className="sd-form-label">
                年份
                <select className="sd-form-select" value={selectedYear}
                  onChange={(e) => { setSelectedYear(e.target.value); handleResetWorkflow() }}
                  disabled={isRunning || sending}>
                  {module.supportedYears.map((y) => (<option key={y} value={y}>{y}</option>))}
                </select>
              </label>
              <button type="button" className="sd-btn sd-btn--run" onClick={handleRunModel} disabled={!canRun}>
                {isRunning || sending ? '运行中…' : '开始运行'}
              </button>
              <button type="button" className="sd-btn sd-btn--match" onClick={handleResetWorkflow} disabled={isRunning || sending}>
                重置
              </button>
            </div>
          </section>

          <MiniMapboxPanel selectedRegion={selectedRegion} session={session} />
        </aside>

        <ResultPanel
          session={session}
          sending={sending}
          apiError={apiError}
          selectedRegion={selectedRegion}
          selectedYear={selectedYear}
          module={module}
        />
      </div>
    </div>
  )
}

export default SolutionDetail
