/**
 * React 19's react-dom/server expects browser/Node globals that CRA's Jest
 * environment provided. Polyfill what jsdom omits for renderToStaticMarkup tests.
 */
const { TextEncoder, TextDecoder } = require("util");
if (typeof globalThis.TextEncoder === "undefined") globalThis.TextEncoder = TextEncoder;
if (typeof globalThis.TextDecoder === "undefined") globalThis.TextDecoder = TextDecoder;

if (typeof globalThis.MessageChannel === "undefined") {
  class MockMessagePort {
    constructor() {
      this.onmessage = null;
      this._peer = null;
    }
    postMessage(data) {
      const peer = this._peer;
      if (!peer) return;
      queueMicrotask(() => {
        if (typeof peer.onmessage === "function") {
          peer.onmessage({ data });
        }
      });
    }
    close() {}
  }
  class MockMessageChannel {
    constructor() {
      this.port1 = new MockMessagePort();
      this.port2 = new MockMessagePort();
      this.port1._peer = this.port2;
      this.port2._peer = this.port1;
    }
  }
  globalThis.MessageChannel = MockMessageChannel;
}
