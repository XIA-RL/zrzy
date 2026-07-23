import React from 'react'
import { useNavigate } from 'react-router-dom'
import './Home.css'

function Home() {
  const navigate = useNavigate()

  return (
    <div className="home">
      <section className="hero">
        <div className="hero-main">
          <div className="hero-top">
            <h1 className="hero-title">
              <span className="hero-title-line">自然资源调查数据分析评估系统</span>
            </h1>
            <p className="hero-desc">
              <span className="hero-desc-line">集成 InVEST 、 NDVI 、 SWAT等多种模型，支持全国任意县/区的自然资源调查数据智能化分析与综合评估。</span>
            </p>
            <div className="hero-feature-grid" aria-label="平台核心能力">
              <div className="hero-feature-card">
                <span className="hero-feature-label">AI 智能体</span>
                <strong>自然语言驱动全流程分析</strong>
              </div>
              <div className="hero-feature-card">
                <span className="hero-feature-label">GIS 自动化</span>
                <strong>多源数据处理与空间分析</strong>
              </div>
              <div className="hero-feature-card">
                <span className="hero-feature-label">多模型集成</span>
                <strong>InVEST、NDVI、SWAT等</strong>
              </div>
              <div className="hero-feature-card">
                <span className="hero-feature-label">动态监测</span>
                <strong>多年份对比与趋势分析</strong>
              </div>
            </div>
            <div className="hero-actions">
              <button type="button" className="hero-cta" onClick={() => navigate('/agent')}>
                进入 AI 智能体
              </button>
              <button type="button" className="hero-cta" onClick={() => navigate('/solutions')}>
                进入技术方案
              </button>
            </div>
          </div>

          <div className="hero-visual">
            <div className="hero-visual-grid">
              <div className="hero-quadrant hero-quadrant-tl" aria-hidden="true" />

              <div className="hero-quadrant hero-quadrant-tr hero-video">
                <div className="hero-video-slot">
                  <video
                    className="hero-video-player"
                    src="/OpenGMS 生态智算小队_EcoInvest-GPT——生态环境监测数据智能化分析平台_项目视频.mp4"
                    controls
                    playsInline
                    preload="metadata"
                  >
                    您的浏览器不支持视频播放。
                  </video>
                </div>
              </div>

              <div className="hero-quadrant hero-quadrant-bl hero-flowchart">
                <div className="hero-flowchart-frame">
                  <img
                    src="/配图.png"
                    alt="自然资源调查监测数据智能化分析平台流程图"
                    className="hero-flowchart-img"
                    decoding="async"
                    fetchPriority="high"
                  />
                </div>
              </div>

              <div className="hero-quadrant hero-quadrant-br" aria-hidden="true" />
            </div>

            <div className="hero-visual-crosshair" aria-hidden="true">
              <span className="hero-crosshair-h" />
              <span className="hero-crosshair-v" />
              <span className="hero-crosshair-dot" />
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

export default Home
