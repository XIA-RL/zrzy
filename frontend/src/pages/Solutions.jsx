import React, { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { INVEST_MODULES, CATEGORIES } from '../data/investModules'
import './Solutions.css'

const CATEGORY_ICONS = {
  all: (
    <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16">
      <path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zM11 13a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
    </svg>
  ),
  terrestrial: (
    <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16">
      <path fillRule="evenodd" d="M4.083 9h1.946c.089-1.546.383-2.97.837-4.118A6.004 6.004 0 004.083 9zM10 2a8 8 0 100 16A8 8 0 0010 2zm0 2c-.076 0-.232.032-.465.262-.238.234-.497.623-.737 1.182-.389.907-.673 2.142-.766 3.556h3.936c-.093-1.414-.377-2.649-.766-3.556-.24-.559-.499-.948-.737-1.182C10.232 4.032 10.076 4 10 4zm3.971 5c-.089-1.546-.383-2.97-.837-4.118A6.004 6.004 0 0115.917 9h-1.946zm-2.003 2H8.032c.093 1.414.377 2.649.766 3.556.24.559.499.948.737 1.182.233.23.389.262.465.262.076 0 .232-.032.465-.262.238-.234.498-.623.737-1.182.389-.907.673-2.142.766-3.556zm1.166 4.118c.454-1.147.748-2.572.837-4.118h1.946a6.004 6.004 0 01-2.783 4.118zm-6.268 0C6.412 13.97 6.118 12.546 6.03 11H4.083a6.004 6.004 0 002.783 4.118z" clipRule="evenodd" />
    </svg>
  ),
  freshwater: (
    <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16">
      <path fillRule="evenodd" d="M5.5 16.5a1 1 0 01-1-1v-5a1 1 0 011-1h9a1 1 0 011 1v5a1 1 0 01-1 1h-9zm-3-8a1 1 0 000 2h.5V16.5a2.5 2.5 0 002.5 2.5h9a2.5 2.5 0 002.5-2.5V10.5h.5a1 1 0 000-2h-15zM10 3a1 1 0 011 1v1h1a1 1 0 110 2h-4a1 1 0 010-2h1V4a1 1 0 011-1z" clipRule="evenodd" />
    </svg>
  ),
  marine: (
    <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16">
      <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z" />
    </svg>
  ),
  urban: (
    <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16">
      <path fillRule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a1 1 0 110 2h-3a1 1 0 01-1-1v-2a1 1 0 00-1-1H9a1 1 0 00-1 1v2a1 1 0 01-1 1H4a1 1 0 110-2V4zm3 1h2v2H7V5zm2 4H7v2h2V9zm2-4h2v2h-2V5zm2 4h-2v2h2V9z" clipRule="evenodd" />
    </svg>
  ),
  supporting: (
    <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16">
      <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
    </svg>
  ),
}

function ModuleRow({ module }) {
  const isAvailable = module.status === 'available'

  return (
    <div className={`module-row ${isAvailable ? 'module-row--available' : 'module-row--disabled'}`}>
      <div className="module-row-info">
        <div className="module-row-names">
          <span className="module-row-name">{module.name}</span>
          <span className="module-row-name-en">{module.nameEn}</span>
        </div>
        <p className="module-row-summary">{module.summary}</p>
        <div className="module-row-tags">
          {module.tags.slice(0, 3).map((tag) => (
            <span key={tag} className="module-tag">{tag}</span>
          ))}
        </div>
      </div>
      <div className="module-row-action">
        {isAvailable ? (
          <Link to={`/solutions/${module.id}`} className="module-btn module-btn--primary">
            查看详情
          </Link>
        ) : (
          <span className="module-badge--soon">即将上线</span>
        )}
      </div>
    </div>
  )
}

function Solutions() {
  const [activeCategory, setActiveCategory] = useState('all')
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const byCategory = activeCategory === 'all'
      ? INVEST_MODULES
      : INVEST_MODULES.filter((m) => m.category === activeCategory)
    if (!q) return byCategory
    return byCategory.filter(
      (m) =>
        m.name.toLowerCase().includes(q) ||
        m.nameEn.toLowerCase().includes(q) ||
        m.summary.toLowerCase().includes(q) ||
        m.tags.some((t) => t.toLowerCase().includes(q)),
    )
  }, [activeCategory, query])

  const countByCategory = useMemo(() => {
    const map = { all: INVEST_MODULES.length }
    CATEGORIES.forEach((c) => {
      if (c.id !== 'all') {
        map[c.id] = INVEST_MODULES.filter((m) => m.category === c.id).length
      }
    })
    return map
  }, [])

  return (
    <div className="sol-page">
      {/* ── 顶部概览区 ── */}
      <div className="sol-top">
        <div className="sol-hero">
          <div className="sol-hero-main">
            <div className="sol-hero-title-row">
              <h1 className="sol-top-title">模型技术方案</h1>
              <span className="sol-hero-kicker">Technology Solutions</span>
            </div>
            <p className="sol-hero-desc">
              面向生态系统服务评估的模型工具库，覆盖陆地、淡水、海洋与海岸带、城市生态和辅助支撑工具。
            </p>
          </div>
        </div>
      </div>

      {/* ── 下方主体：左侧目录 + 右侧内容 ── */}
      <div className="sol-body">
        {/* Left sidebar */}
        <aside className="sol-sidebar">
          <p className="sol-nav-section-label">模块分类</p>
          <nav className="sol-nav">
            {CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                type="button"
                className={`sol-nav-item ${activeCategory === cat.id ? 'sol-nav-item--active' : ''}`}
                onClick={() => { setActiveCategory(cat.id); setQuery('') }}
              >
                <span className="sol-nav-label-cn">{cat.label}</span>
                <span className="sol-nav-count">{countByCategory[cat.id]}</span>
              </button>
            ))}
          </nav>
        </aside>

        {/* Right content */}
        <main className="sol-main">
          {/* Search bar — 撑满右侧容器 */}
          <div className="sol-search-bar">
            <div className="sol-search-wrap">
              <svg className="sol-search-icon" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
              </svg>
              <input
                type="search"
                className="sol-search-input"
                placeholder="搜索模块名称或关键词…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <button type="button" className="sol-search-btn">搜索</button>
          </div>

          {/* Category title + count */}
          <div className="sol-content-header">
            <span className="sol-content-category">
              {CATEGORIES.find((c) => c.id === activeCategory)?.label}
            </span>
            <span className="sol-content-count">{filtered.length} 个模块</span>
          </div>

          {/* Module list */}
          {filtered.length === 0 ? (
            <div className="sol-empty">未找到匹配的模块，请尝试其他关键词。</div>
          ) : (
            <div className="sol-list">
              {filtered.map((module) => (
                <ModuleRow key={module.id} module={module} />
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}

export default Solutions
