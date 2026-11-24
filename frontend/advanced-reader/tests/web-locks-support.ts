/** Platform substitute for jsdom only; exclusivity is verified with actual browser popups. */
import { vi } from "vitest";
export function mockWindowLocks() {
  Object.defineProperty(navigator, "locks", {
    configurable: true,
    value: {
      request: vi.fn(
        async (
          name: string,
          _options: unknown,
          callback: (lock: object) => unknown,
        ) => callback({ name, mode: "exclusive" }),
      ),
    },
  });
}
