// Dependency-free CDP transport; orchestration stays in Python.
import { readFileSync } from 'node:fs';
const input = JSON.parse(readFileSync(0, 'utf8'));
const ws = new WebSocket(input.ws);
let serial = 0;
const pending = new Map();
const events = [];
ws.addEventListener('message', ({ data }) => {
  const packet = JSON.parse(data);
  if (packet.id && pending.has(packet.id)) {
    const { resolve, reject, timer } = pending.get(packet.id);
    clearTimeout(timer);
    pending.delete(packet.id);
    packet.error ? reject(new Error(JSON.stringify(packet.error))) : resolve(packet.result);
  } else if (input.collectEvents) events.push(packet);
});
function rpc(method, params = {}) {
  const id = ++serial;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, input.timeoutMs || 20000);
    pending.set(id, { resolve, reject, timer });
    ws.send(JSON.stringify({ id, method, params }));
  });
}
try {
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true });
    ws.addEventListener('error', reject, { once: true });
  });
  const results = [];
  for (const command of input.commands) {
    try { results.push({ ok: true, method: command.method, result: await rpc(command.method, command.params) }); }
    catch (error) { results.push({ ok: false, method: command.method, error: String(error) }); }
  }
  console.log(JSON.stringify({ results, events }));
} catch (error) { console.log(JSON.stringify({ error: String(error) })); process.exitCode = 1; }
finally { ws.close(); }
