import "@testing-library/jest-dom/vitest";

class BroadcastChannelPoly {
  postMessage() {}
  addEventListener() {}
  removeEventListener() {}
  close() {}
}
if (typeof window !== "undefined" && !("BroadcastChannel" in window)) {
  (window as unknown as Record<string, unknown>).BroadcastChannel = BroadcastChannelPoly;
}
