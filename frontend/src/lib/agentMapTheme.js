/** 与 Agent 浅色主题一致的地图配色 */
export const MAP_THEME = {
  bg: '#f8fafc',
  water: '#dbeafe',
  land: '#f1f5f9',
  landAlt: '#e2e8f0',
  building: '#cbd5e1',
  roadMinor: '#cbd5e1',
  roadMajor: '#0284c7',
  boundary: '#0ea5e9',
  label: '#64748b',
  labelHalo: '#ffffff',
}

const WATER_RE = /water|waterway|ocean|sea|river|lake|reservoir|marine/i
const LAND_RE = /land|landcover|landuse|park|pitch|grass|wood|scrub|snow|hillshade/i
const ROAD_RE = /road|street|path|bridge|tunnel|motorway|trunk|primary|secondary|tertiary/i
/** Mapbox 内置行政区/边界图层（与自有 shp 不对齐，全部隐藏） */
const ADMIN_BOUNDARY_HIDE_RE =
  /admin|boundary|disputed|maritime|territory|country-|state-|province|county|region-/i
const LABEL_RE = /label|place|road-name|poi|settlement/i

/**
 * 在 light-v11 底图上覆写为平台浅色主题
 */
export function applyAgentBlueTheme(map) {
  const paint = () => {
    const style = map.getStyle()
    if (!style?.layers) return

    for (const layer of style.layers) {
      const { id, type } = layer
      try {
        /* 隐藏 Mapbox 自带边界，仅保留业务 GeoJSON 边界 */
        if (ADMIN_BOUNDARY_HIDE_RE.test(id)) {
          map.setLayoutProperty(id, 'visibility', 'none')
          continue
        }

        if (type === 'background') {
          map.setPaintProperty(id, 'background-color', MAP_THEME.bg)
          continue
        }

        if (type === 'fill') {
          if (WATER_RE.test(id)) {
            map.setPaintProperty(id, 'fill-color', MAP_THEME.water)
          } else if (LAND_RE.test(id)) {
            map.setPaintProperty(id, 'fill-color', MAP_THEME.landAlt)
          } else if (/building|structure|airport/i.test(id)) {
            map.setPaintProperty(id, 'fill-color', MAP_THEME.building)
            map.setPaintProperty(id, 'fill-opacity', 0.55)
          }
          continue
        }

        if (type === 'line') {
          if (WATER_RE.test(id)) {
            map.setPaintProperty(id, 'line-color', '#93c5fd')
          } else if (ROAD_RE.test(id)) {
            const major = /motorway|trunk|primary|bridge/i.test(id)
            map.setPaintProperty(id, 'line-color', major ? MAP_THEME.roadMajor : MAP_THEME.roadMinor)
            map.setPaintProperty(id, 'line-opacity', major ? 0.7 : 0.5)
          }
          continue
        }

        if (type === 'symbol' && LABEL_RE.test(id)) {
          map.setPaintProperty(id, 'text-color', MAP_THEME.label)
          map.setPaintProperty(id, 'text-halo-color', MAP_THEME.labelHalo)
          map.setPaintProperty(id, 'text-halo-width', 1.2)
        }
      } catch {
        /* 个别图层只读，忽略 */
      }
    }

    if (typeof map.setFog === 'function') {
      map.setFog({
        color: 'rgb(248, 250, 252)',
        'high-color': 'rgb(226, 232, 240)',
        'horizon-blend': 0.08,
        'space-color': MAP_THEME.bg,
        'star-intensity': 0,
      })
    }
  }

  if (map.__agentBlueThemeApplied) return
  map.__agentBlueThemeApplied = true

  if (map.isStyleLoaded()) {
    paint()
  } else {
    map.once('load', paint)
  }
  map.on('style.load', paint)
}

export const AGENT_MAP_STYLE = 'mapbox://styles/mapbox/light-v11'
