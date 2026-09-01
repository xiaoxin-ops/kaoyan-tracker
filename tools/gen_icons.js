// 生成 PWA 图标（纯 Node，无依赖）：莫兰迪鼠尾草绿底 + 白色圆 + 幼苗图案
// 用法：node tools/gen_icons.js
const zlib = require('zlib');
const fs = require('fs');
const path = require('path');

// ---------- PNG 编码 ----------
const CRC_TABLE = (() => {
  const t = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
})();
function crc32(buf) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}
function encodePNG(width, height, rgba) {
  const sig = Buffer.from([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;   // bit depth
  ihdr[9] = 6;   // RGBA
  const raw = Buffer.alloc((width * 4 + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (width * 4 + 1)] = 0; // filter: none
    rgba.copy(raw, y * (width * 4 + 1) + 1, y * width * 4, (y + 1) * width * 4);
  }
  return Buffer.concat([
    sig,
    chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

// ---------- 绘制（2x 超采样抗锯齿） ----------
const SAGE = [0xA3, 0xB1, 0x8A];       // 背景
const WHITE = [0xFF, 0xFF, 0xFF];
const SPROUT = [0x7E, 0x91, 0x66];     // 幼苗（sage-deep）

function sample(x, y, S) {
  // x,y 为 0..S 坐标；返回 RGBA
  const corner = S * 0.22;
  const inRounded = (px, py) => {
    const cx = Math.min(Math.max(px, corner), S - corner);
    const cy = Math.min(Math.max(py, corner), S - corner);
    const dx = px - cx, dy = py - cy;
    return Math.hypot(dx, dy) <= corner || (px >= corner && px <= S - corner) || (py >= corner && py <= S - corner);
  };
  if (!inRounded(x, y)) return [0, 0, 0, 0];

  let [r, g, b] = SAGE;
  const cx = S / 2, cy = S / 2;
  // 白色圆盘（留出 maskable 安全边距：圆半径 0.40S）
  if (Math.hypot(x - cx, y - cy) <= S * 0.40) {
    [r, g, b] = WHITE;
  }
  // 幼苗：茎 + 两片叶子
  const stemW = S * 0.024;
  const stemTop = cy - S * 0.02, stemBottom = cy + S * 0.20;
  if (Math.abs(x - cx) <= stemW && y >= stemTop && y <= stemBottom) {
    [r, g, b] = SPROUT;
  }
  const leafR = S * 0.125;
  const leafY = cy - S * 0.05;
  const leafOff = S * 0.145;
  for (const dx of [-leafOff, leafOff]) {
    if (Math.hypot(x - (cx + dx), y - leafY) <= leafR) [r, g, b] = SPROUT;
  }
  // 茎底小横线（土壤）
  if (Math.abs(y - stemBottom) <= S * 0.012 && Math.abs(x - cx) <= S * 0.075) {
    [r, g, b] = SPROUT;
  }
  return [r, g, b, 255];
}

function render(size) {
  const S = size * 2; // 超采样
  const big = Buffer.alloc(S * S * 4);
  for (let y = 0; y < S; y++) {
    for (let x = 0; x < S; x++) {
      const [r, g, b, a] = sample(x + 0.5, y + 0.5, S);
      const i = (y * S + x) * 4;
      big[i] = r; big[i + 1] = g; big[i + 2] = b; big[i + 3] = a;
    }
  }
  const out = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let r = 0, g = 0, b = 0, a = 0;
      for (let dy = 0; dy < 2; dy++) {
        for (let dx = 0; dx < 2; dx++) {
          const i = ((y * 2 + dy) * S + (x * 2 + dx)) * 4;
          r += big[i]; g += big[i + 1]; b += big[i + 2]; a += big[i + 3];
        }
      }
      const o = (y * size + x) * 4;
      out[o] = Math.round(r / 4); out[o + 1] = Math.round(g / 4);
      out[o + 2] = Math.round(b / 4); out[o + 3] = Math.round(a / 4);
    }
  }
  return encodePNG(size, size, out);
}

const outDir = path.join(__dirname, '..', 'static', 'icons');
fs.mkdirSync(outDir, { recursive: true });
for (const size of [192, 512]) {
  const file = path.join(outDir, `icon-${size}.png`);
  fs.writeFileSync(file, render(size));
  console.log('生成', file, fs.statSync(file).size, 'bytes');
}
