/**
 * Installed with BrowserContext.addInitScript before the first navigation.
 * Dedicated/shared workers and transports outside Playwright's HTTP/WebSocket
 * routing are intentionally unavailable in this proof. EventSource is also
 * unavailable: the application uses its real HTTP polling fallback, allowing
 * every HTTP request to be forwarded without redirects.
 *
 * The optional target exists only to make the guard deterministic in Node unit
 * tests. Playwright calls the function with the default globalThis target.
 */
export function installBrowserRuntimeGuard(_options = {}, target = globalThis) {
  for (const constructorName of [
    "Worker",
    "SharedWorker",
    "WebTransport",
    "RTCPeerConnection",
    "webkitRTCPeerConnection",
    "WebSocketStream",
  ]) {
    const BlockedWorker = class {
      constructor() {
        throw new Error(`${constructorName} est désactivé par la frontière E2E.`);
      }
    };
    Object.defineProperty(target, constructorName, {
      configurable: false,
      enumerable: false,
      value: BlockedWorker,
      writable: false,
    });
  }
  Object.defineProperty(target, "EventSource", {
    configurable: false,
    enumerable: false,
    value: undefined,
    writable: false,
  });
}
