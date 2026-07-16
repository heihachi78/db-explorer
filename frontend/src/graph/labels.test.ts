import { expect, test } from "vitest";

import { compactObjectLabel } from "./labels";


test("keeps short object labels intact", () => {
  expect(compactObjectLabel("SALES", "ORDERS")).toBe("SALES.ORDERS");
});


test("compacts long Oracle object labels to a predictable maximum", () => {
  const publicLabel = compactObjectLabel("PUBLIC", "WLM_METRICS_STREAM");
  const longOwnerLabel = compactObjectLabel("VERY_LONG_APPLICATION_OWNER", "ORDER_PROCESSING_PACKAGE");

  expect(publicLabel).toBe("PUBLIC.WLM_METRICS_STRE…");
  expect(publicLabel).toHaveLength(24);
  expect(longOwnerLabel).toHaveLength(24);
  expect(longOwnerLabel).toMatch(/…\..+…$/);
});
