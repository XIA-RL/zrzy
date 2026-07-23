/**
 * Optional asset sync hook (predev / prebuild).
 * Demo videos are large and usually not in git; warn if absent.
 */
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const publicDir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'public')
const videos = [
  'demo.mp4',
  'OpenGMS 生态智算小队_EcoInvest-GPT——生态环境监测数据智能化分析平台_项目视频.mp4',
]

const missing = videos.filter((name) => !existsSync(path.join(publicDir, name)))
if (missing.length) {
  console.warn(
    `[copy-demo-video] missing video(s) in public/: ${missing.join(', ')} — homepage video slot may be empty (optional)`,
  )
}
