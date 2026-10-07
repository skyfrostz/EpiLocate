// Deterministic, synthetic-only Explicit VR Little Endian CT fixtures.
// Equivalent pixel/geometry parameters to create_fixture.py; no Python packages needed.
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const output = join(dirname(fileURLToPath(import.meta.url)), '..', '.local')
const longVr = new Set(['OB', 'OW', 'UN'])
function tag(group, element, vr, value) {
  let bytes = Buffer.isBuffer(value) ? value : Buffer.from(value, 'ascii')
  if (bytes.length % 2) bytes = Buffer.concat([bytes, Buffer.from([vr === 'UI' ? 0 : 32])])
  const header = Buffer.alloc(longVr.has(vr) ? 12 : 8)
  header.writeUInt16LE(group, 0)
  header.writeUInt16LE(element, 2)
  header.write(vr, 4, 2, 'ascii')
  if (longVr.has(vr)) header.writeUInt32LE(bytes.length, 8)
  else header.writeUInt16LE(bytes.length, 6)
  return Buffer.concat([header, bytes])
}
function us(value) { const bytes = Buffer.alloc(2); bytes.writeUInt16LE(value); return bytes }
function make(oriented) {
  const uid = oriented ? '2.25.18499269058459638566132766337321489010' : '2.25.18499269058459638566132766337321489011'
  const sop = '1.2.840.10008.5.1.4.1.1.2'
  const meta = Buffer.concat([
    tag(2, 1, 'OB', Buffer.from([0, 1])), tag(2, 2, 'UI', sop), tag(2, 3, 'UI', uid),
    tag(2, 0x10, 'UI', '1.2.840.10008.1.2.1'), tag(2, 0x12, 'UI', '2.25.18499269058459638566132766337321489012'),
  ])
  const metaLength = Buffer.alloc(4); metaLength.writeUInt32LE(meta.length)
  const pixels = Buffer.alloc(112 * 80 * 2)
  for (let row = 0; row < 80; row++) for (let col = 0; col < 112; col++) {
    pixels.writeUInt16LE(400 + 250 * ((Math.floor(row / 10) + Math.floor(col / 14)) % 2) + row * 8, (row * 112 + col) * 2)
  }
  const dataset = [tag(8, 0x16, 'UI', sop), tag(8, 0x18, 'UI', uid), tag(8, 0x60, 'CS', 'CT'),
    tag(0x10, 0x10, 'PN', 'SYNTHETIC^GEOMETRY'), tag(0x10, 0x20, 'LO', 'SYNTHETIC-ONLY')]
  if (oriented) dataset.push(tag(0x20, 0x32, 'DS', '12\\34\\56'), tag(0x20, 0x37, 'DS', '0\\1\\0\\-1\\0\\0'))
  dataset.push(tag(0x28, 2, 'US', us(1)), tag(0x28, 4, 'CS', 'MONOCHROME2'),
    tag(0x28, 0x10, 'US', us(80)), tag(0x28, 0x11, 'US', us(112)))
  if (oriented) dataset.push(tag(0x28, 0x30, 'DS', '0.7\\1.2'))
  dataset.push(tag(0x28, 0x100, 'US', us(16)), tag(0x28, 0x101, 'US', us(16)),
    tag(0x28, 0x102, 'US', us(15)), tag(0x28, 0x103, 'US', us(0)),
    tag(0x28, 0x1050, 'DS', '-400'), tag(0x28, 0x1051, 'DS', '1200'),
    tag(0x28, 0x1052, 'DS', '-1024'), tag(0x28, 0x1053, 'DS', '1'), tag(0x7fe0, 0x10, 'OW', pixels))
  return Buffer.concat([Buffer.alloc(128), Buffer.from('DICM'), tag(2, 0, 'UL', metaLength), meta, ...dataset])
}
await mkdir(output, { recursive: true })
await writeFile(join(output, 'geometry_synthetic_ct.dcm'), make(false))
await writeFile(join(output, 'geometry_synthetic_oriented_ct.dcm'), make(true))
console.log('Generated synthetic-only CT fixtures in frontend/.local')
