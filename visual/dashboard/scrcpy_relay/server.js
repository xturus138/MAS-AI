/**
 * visual/dashboard/scrcpy_relay/server.js
 *
 * Minimal ADB screenrecord → WebSocket relay.
 * Streams raw H.264 NAL units from `adb exec-out screenrecord --output-format=h264`
 * to browser clients as binary WebSocket frames.
 * Browser decodes with Broadway.js (bundled WASM, zero install on client).
 *
 * Usage:
 *   node server.js [DEVICE_ID] [PORT]
 *   e.g. node server.js 150.65.51.192:34425 8000
 *
 * Dependencies: ws  (npm install ws)
 */

const { WebSocketServer } = require('ws');
const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');
const path = require('path');

const DEVICE = process.env.DEVICE || process.argv[2] || '';
const PORT   = parseInt(process.env.PORT || process.argv[3] || '8000', 10);
const PUBLIC = path.join(__dirname, 'public');

// ── Tiny static HTTP server for Broadway player page ─────────────────
const httpServer = http.createServer((req, res) => {
  let filePath = path.join(PUBLIC, req.url === '/' ? 'player.html' : req.url);
  const ext = path.extname(filePath).toLowerCase();
  const mime = {
    '.html': 'text/html', '.js': 'application/javascript',
    '.wasm': 'application/wasm', '.css': 'text/css',
  }[ext] || 'application/octet-stream';

  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); res.end('Not found'); return; }
    res.writeHead(200, { 'Content-Type': mime });
    res.end(data);
  });
});

// ── WebSocket server: broadcast ADB H.264 stream ─────────────────────
const wss = new WebSocketServer({ server: httpServer });
let adbProc = null;
const clients = new Set();

wss.on('connection', (ws) => {
  clients.add(ws);
  console.log(`[relay] Client connected (total: ${clients.size})`);

  // Start ADB stream when first client connects
  if (clients.size === 1) startAdb();

  ws.on('close', () => {
    clients.delete(ws);
    console.log(`[relay] Client disconnected (total: ${clients.size})`);
    if (clients.size === 0) stopAdb();
  });
});

function startAdb() {
  const args = DEVICE ? ['-s', DEVICE] : [];
  // screenrecord: unlimited time, raw H.264, pipe to stdout
  // --time-limit 0 not supported on all Android versions; omit → default 3 min max per segment
  // We restart automatically on exit.
  const cmd = ['adb', ...args, 'exec-out', 'screenrecord',
                '--output-format=h264', '--size', '720x1280', '-'];
  console.log('[relay] Starting:', cmd.join(' '));
  adbProc = spawn(cmd[0], cmd.slice(1), { stdio: ['ignore', 'pipe', 'pipe'] });

  adbProc.stdout.on('data', (chunk) => {
    for (const ws of clients) {
      if (ws.readyState === ws.OPEN) ws.send(chunk);
    }
  });

  adbProc.stderr.on('data', (d) => console.error('[adb]', d.toString().trim()));

  adbProc.on('exit', (code) => {
    console.log(`[relay] adb exited (${code}). Restarting in 2s…`);
    adbProc = null;
    if (clients.size > 0) setTimeout(startAdb, 2000);
  });
}

function stopAdb() {
  if (adbProc) { adbProc.kill(); adbProc = null; }
}

httpServer.listen(PORT, () => {
  console.log(`[relay] Listening on http://localhost:${PORT}`);
  console.log(`[relay] Device: ${DEVICE || '(auto)'}`);
});
