import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { installBrowserRuntimeGuard } from "../lib/browser-runtime-guard.mjs";

describe("installBrowserRuntimeGuard", () => {
  test("remplace les workers et transports hors routage par des constructeurs bloquants", () => {
    const target = {
      RTCPeerConnection: class OriginalRTCPeerConnection {},
      SharedWorker: class OriginalSharedWorker {},
      WebSocketStream: class OriginalWebSocketStream {},
      WebTransport: class OriginalWebTransport {},
      Worker: class OriginalWorker {},
      webkitRTCPeerConnection: class OriginalWebkitRTCPeerConnection {},
    };

    installBrowserRuntimeGuard({}, target);

    for (const name of [
      "Worker",
      "SharedWorker",
      "WebTransport",
      "RTCPeerConnection",
      "webkitRTCPeerConnection",
      "WebSocketStream",
    ]) {
      assert.throws(() => Reflect.construct(target[name], []), new RegExp(`${name} est désactivé`));
    }
  });

  test("rend tous les remplacements non réactivables par le code applicatif", () => {
    const target = {};
    installBrowserRuntimeGuard({}, target);

    for (const name of [
      "Worker",
      "SharedWorker",
      "WebTransport",
      "RTCPeerConnection",
      "webkitRTCPeerConnection",
      "WebSocketStream",
    ]) {
      assert.deepEqual(Object.getOwnPropertyDescriptor(target, name), {
        configurable: false,
        enumerable: false,
        value: target[name],
        writable: false,
      });
      assert.throws(() => Object.defineProperty(target, name, { value: class {} }), TypeError);
    }
  });

  test("désactive EventSource pour imposer le polling HTTP borné", () => {
    const target = { EventSource: class OriginalEventSource {} };
    installBrowserRuntimeGuard({}, target);

    assert.equal(target.EventSource, undefined);
    assert.deepEqual(Object.getOwnPropertyDescriptor(target, "EventSource"), {
      configurable: false,
      enumerable: false,
      value: undefined,
      writable: false,
    });
  });
});
