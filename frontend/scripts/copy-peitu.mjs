/**
 * Optional asset sync hook (predev / prebuild).
 * 配图 already lives in public/; this script only warns if missing.
 */
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const publicDir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'public')
const target = path.join(publicDir, '配图.png')

if (!existsSync(target)) {
  console.warn('[copy-peitu] missing public/配图.png — homepage flowchart will be blank')
}
