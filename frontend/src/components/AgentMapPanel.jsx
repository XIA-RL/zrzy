import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Map, { Layer, Source } from 'react-map-gl/mapbox'
import 'mapbox-gl/dist/mapbox-gl.css'
import { AGENT_MAP_STYLE, applyAgentBlueTheme } from '../lib/agentMapTheme'
import './AgentMapPanel.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
const DEFAULT_CENTER = { longitude: 119.68, latitude: 30.63, zoom: 9 }

const MAP_LAYER_CHIPS = [
  { id: 'clip', label: '裁剪结果' },
  { id: 'reclass', label: '重分类结果' },
  { id: 'habitat', label: '生境质量评分' },
  { id: 'carbon', label: '碳储量分布' },
]

const BOUNDARY_PAINT = {
  fill: {
    'fill-color': '#0ea5e9',
    'fill-opacity': 0.15,
  },
  line: {
    'line-color': '#0284c7',
    'line-width': 1.5,
    'line-opacity': 0.85,
  },
}

/** 从 session 产物推断应在地图上展示的图层 */
export function buildMapLayers(session) {
  if (!session?.id) return []

  const layers = []
  const year = session.plan?.year
  const artifacts = session.artifacts || {}
  const models = session.plan?.models || []
  const state = session.state

  if (year && (artifacts.clipped_tif || artifacts.clip_preview)) {
    layers.push({
      id: 'clip',
      label: '裁剪结果',
      type: 'raster',
      artifact: `clip_${year}_overlay.png`,
      opacity: 0.92,
    })
  }

  if (year && (artifacts.reclass_tif || artifacts.reclass_preview)) {
    layers.push({
      id: 'reclass',
      label: '重分类结果',
      type: 'raster',
      artifact: `lulc_${year}_overlay.png`,
      opacity: 0.92,
    })
  }

  // InVEST 成果在 DONE 后写入 session 目录
  const investReady = state === 'DONE'
  if (year && investReady && (models.includes('habitat_quality') || !models.length)) {
    layers.push({
      id: 'habitat',
      label: '生境质量评分',
      type: 'raster',
      artifact: `habitat_quality_${year}_overlay.png`,
      opacity: 0.92,
    })
  }

  if (year && investReady && (models.includes('carbon_storage') || !models.length)) {
    layers.push({
      id: 'carbon',
      label: '碳储量分布',
      type: 'raster',
      artifact: `carbon_storage_${year}_overlay.png`,
      opacity: 0.92,
    })
  }

  return layers
}

function artifactUrl(sessionId, name) {
  return `${API_BASE}/api/sessions/${sessionId}/artifacts/${encodeURIComponent(name)}`
}

async function fetchBoundary(regionCode) {
  const resp = await fetch(`${API_BASE}/api/regions/${regionCode}/boundary`)
  if (!resp.ok) throw new Error('boundary fetch failed')
  return resp.json()
}

async function fetchArtifactBounds(sessionId, filename) {
  const resp = await fetch(
    `${API_BASE}/api/sessions/${sessionId}/artifacts/${encodeURIComponent(filename)}/bounds`,
  )
  if (!resp.ok) throw new Error(`bounds fetch failed: ${filename}`)
  return resp.json()
}

function AgentMapPanel({ session }) {
  const mapRef = useRef(null)
  const token = import.meta.env.VITE_MAPBOX_TOKEN || ''
  const [boundary, setBoundary] = useState(null)
  const [overlayLayers, setOverlayLayers] = useState([])
  const [selectedLayerId, setSelectedLayerId] = useState(null)
  const [mapStatus, setMapStatus] = useState('')
  const [viewState, setViewState] = useState(DEFAULT_CENTER)

  const sessionId = session?.id
  const regionCode = session?.plan?.region_code
  const regionName = session?.plan?.region_name
  const parentCity = session?.plan?.parent_city || ''
  const displayRegion = parentCity ? `${parentCity}${regionName || ''}` : (regionName || '空间预览')
  const planYear = session?.plan?.year
  const sessionState = session?.state
  const modelsKey = JSON.stringify(session?.plan?.models || [])
  const hasClip = Boolean(session?.artifacts?.clipped_tif || session?.artifacts?.clip_preview)
  const hasReclass = Boolean(session?.artifacts?.reclass_tif || session?.artifacts?.reclass_preview)

  const rasterLayers = useMemo(
    () => buildMapLayers(session),
    // session 轮询时对象引用会变；用稳定字段驱动图层重建
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sessionId, planYear, sessionState, modelsKey, hasClip, hasReclass],
  )

  useEffect(() => {
    if (!regionCode) {
      setBoundary(null)
      return
    }

    let cancelled = false
    setMapStatus('正在加载行政区边界…')

    fetchBoundary(regionCode)
      .then((data) => {
        if (cancelled) return
        setBoundary(data)
        setMapStatus('')
        const map = mapRef.current
        if (map && data.bounds?.length === 4) {
          map.fitBounds(
            [
              [data.bounds[0], data.bounds[1]],
              [data.bounds[2], data.bounds[3]],
            ],
            { padding: 48, duration: 1200 },
          )
        }
      })
      .catch(() => {
        if (!cancelled) setMapStatus('行政区边界加载失败')
      })

    return () => {
      cancelled = true
    }
  }, [regionCode])

  useEffect(() => {
    setSelectedLayerId(null)
    setOverlayLayers([])
  }, [sessionId])

  useEffect(() => {
    if (!sessionId || rasterLayers.length === 0) {
      setOverlayLayers([])
      return
    }

    let cancelled = false

    ;(async () => {
      const loaded = []
      for (const layer of rasterLayers) {
        try {
          const meta = await fetchArtifactBounds(sessionId, layer.artifact)
          loaded.push({
            ...layer,
            url: artifactUrl(sessionId, layer.artifact),
            coordinates: meta.coordinates,
          })
        } catch {
          /* 忽略尚未生成或无法定位的图层 */
        }
      }
      if (!cancelled) {
        setOverlayLayers(loaded)
        setSelectedLayerId((cur) => {
          if (cur && loaded.some((l) => l.id === cur)) return cur
          return loaded.length > 0 ? loaded[loaded.length - 1].id : null
        })
      }
    })()

    return () => {
      cancelled = true
    }
  }, [sessionId, rasterLayers])

  const displayRaster = useMemo(
    () => overlayLayers.find((l) => l.id === selectedLayerId) ?? null,
    [overlayLayers, selectedLayerId],
  )

  const handleSelectLayer = useCallback(
    (layerId) => {
      if (!overlayLayers.some((l) => l.id === layerId)) return
      setSelectedLayerId(layerId)
    },
    [overlayLayers],
  )

  const onMapLoad = useCallback(
    (evt) => {
      const map = evt.target
      mapRef.current = map
      applyAgentBlueTheme(map)
      if (boundary?.bounds?.length === 4) {
        map.fitBounds(
          [
            [boundary.bounds[0], boundary.bounds[1]],
            [boundary.bounds[2], boundary.bounds[3]],
          ],
          { padding: 48, duration: 0 },
        )
      }
    },
    [boundary],
  )

  if (!token) {
    return (
      <aside className="agent-map-panel agent-map-panel--idle">
        <div className="agent-map-placeholder agent-map-placeholder--warn">
          <p>请在 frontend/.env 中配置 VITE_MAPBOX_TOKEN 以启用地图</p>
          <p className="agent-map-hint">
            获取 Token：<a href="https://account.mapbox.com/" target="_blank" rel="noreferrer">mapbox.com</a>
          </p>
        </div>
      </aside>
    )
  }

  const availableLayerIds = new Set(overlayLayers.map((l) => l.id))

  return (
    <aside className="agent-map-panel">
      <div className="agent-map-toolbar">
        <div className="agent-map-toolbar-row">
          <span className="agent-map-region-title">
            {displayRegion}
          </span>
          <div className="agent-map-chip-group">
            {MAP_LAYER_CHIPS.map((chip) => {
              const available = availableLayerIds.has(chip.id)
              const selected = selectedLayerId === chip.id
              return (
                <button
                  key={chip.id}
                  type="button"
                  className={`agent-map-chip layer-${chip.id} ${
                    available ? 'available' : ''
                  } ${selected ? 'selected' : ''}`}
                  disabled={!available}
                  onClick={() => handleSelectLayer(chip.id)}
                  title={available ? `显示${chip.label}` : '该步骤结果尚未生成'}
                >
                  {chip.label}
                </button>
              )
            })}
          </div>
        </div>
        {mapStatus && <span className="agent-map-status">{mapStatus}</span>}
      </div>

      <div className="agent-map-canvas">
        <Map
          mapboxAccessToken={token}
          initialViewState={viewState}
          onMove={(evt) => setViewState(evt.viewState)}
          onLoad={onMapLoad}
          mapStyle={AGENT_MAP_STYLE}
          attributionControl={false}
          style={{ width: '100%', height: '100%' }}
        >
          {boundary?.geojson && (
            <Source id="region-boundary" type="geojson" data={boundary.geojson}>
              <Layer id="region-fill" type="fill" paint={BOUNDARY_PAINT.fill} />
              <Layer id="region-line" type="line" paint={BOUNDARY_PAINT.line} />
            </Source>
          )}

          {displayRaster?.coordinates && (
            <Source
              key={displayRaster.id}
              id={`raster-overlay-${displayRaster.id}`}
              type="image"
              url={displayRaster.url}
              coordinates={displayRaster.coordinates}
            >
              <Layer
                id={`raster-overlay-layer-${displayRaster.id}`}
                type="raster"
                paint={{ 'raster-opacity': displayRaster.opacity }}
              />
            </Source>
          )}
        </Map>
      </div>
    </aside>
  )
}

export default AgentMapPanel
