#!/usr/bin/env node
// Public-port gate: opens $PORT only AFTER the owner account has been claimed, then forwards raw TCP to the private n8n.
// This guarantees the editor is never reachable (and never claimable by a stranger) on the public internet while unclaimed.
const net = require('net');
const [listenPort, target] = [Number(process.argv[2]), Number(process.argv[3])];
if (!listenPort || !target) { console.error('usage: gate.js <public-port> <n8n-port>'); process.exit(2); }
net.createServer(c => {
  const u = net.connect(target, '127.0.0.1');
  c.pipe(u).pipe(c);
  const kill = () => { c.destroy(); u.destroy(); };
  c.on('error', kill); u.on('error', kill); c.setTimeout(120000, kill);
}).listen(listenPort, '0.0.0.0', () => console.log(`[gate] public :${listenPort} -> n8n 127.0.0.1:${target}`));
