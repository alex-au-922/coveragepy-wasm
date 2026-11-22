import { once, on } from "node:events";

async function snapshot() {
  const origin = `http://127.0.0.1:${Number(process.argv[1])}`;
  const signal = AbortSignal.timeout(10000);
  const response = await fetch(`${origin}/json/list`, { signal });
  if (!response.ok) throw new Error(`Inspector returned HTTP ${response.status}`);
  const [target] = await response.json();
  if (!target) throw new Error("No local Worker inspector target");

  const socket = new WebSocket(target.webSocketDebuggerUrl, {
    headers: { Origin: origin },
  });
  const messages = on(socket, "message", { signal, close: ["close", "error"] });
  await once(socket, "open", { signal });
  socket.send(JSON.stringify({ id: 1, method: "Runtime.enable" }));

  let requested = false;
  for await (const [message] of messages) {
    const event = JSON.parse(message.data);
    if (event.id === 1 && event.error) throw new Error(JSON.stringify(event.error));
    if (!requested && event.method === "Runtime.executionContextCreated") {
      requested = true;
      socket.send(JSON.stringify({
        id: 2,
        method: "Runtime.evaluate",
        params: {
          contextId: event.params.context.id,
          expression: "globalThis.wasmCoverage()",
          returnByValue: true,
        },
      }));
    } else if (event.id === 2) {
      const data = event.result?.result?.value;
      if (typeof data !== "string") throw new Error(JSON.stringify(event));
      return Buffer.from(data, "base64");
    }
  }
  throw new Error("Inspector closed before returning coverage");
}

try {
  process.stdout.write(await snapshot(), () => process.exit(0));
} catch (error) {
  process.stderr.write(`${error}\n`, () => process.exit(1));
}
