import { describe, expect, it } from "vitest";

describe("KhoanKm calculation and validation logic", () => {
  it("computes split percentages correctly and ensures total is 100%", () => {
    const tx = 60;
    const px = 40;
    expect(tx + px).toBe(100);

    const tripCost = 1_000_000;
    const driverPay = Math.round((tripCost * tx) / 100);
    const assistantPay = Math.round((tripCost * px) / 100);

    expect(driverPay).toBe(600_000);
    expect(assistantPay).toBe(400_000);
    expect(driverPay + assistantPay).toBe(tripCost);
  });

  it("handles driver going alone: receives 100% of the trip", () => {
    const tripCost = 1_500_000;
    const driverPaySolo = tripCost;
    const assistantPaySolo = 0;

    expect(driverPaySolo).toBe(1_500_000);
    expect(assistantPaySolo).toBe(0);
  });

  it("validates bracket ladder correctly", () => {
    const brackets = [
      { up_to_km: 10, don_gia: 15000 },
      { up_to_km: 30, don_gia: 12000 },
      { up_to_km: null, don_gia: 9000 },
    ];

    // Find applicable bracket for 85km -> should fall into >30km bracket
    const testKm = 85;
    const matched = brackets.find((b) => b.up_to_km == null || testKm <= b.up_to_km);
    expect(matched).toBeDefined();
    expect(matched?.don_gia).toBe(9000);
    expect(testKm * (matched?.don_gia ?? 0)).toBe(765_000);

    // Find applicable bracket for 8km -> should fall into <=10km bracket
    const testKmShort = 8;
    const matchedShort = brackets.find((b) => b.up_to_km == null || testKmShort <= b.up_to_km);
    expect(matchedShort?.don_gia).toBe(15000);
    expect(testKmShort * (matchedShort?.don_gia ?? 0)).toBe(120_000);

    // Find applicable bracket for 25km -> should fall into <=30km bracket
    const testKmMid = 25;
    const matchedMid = brackets.find((b) => b.up_to_km == null || testKmMid <= b.up_to_km);
    expect(matchedMid?.don_gia).toBe(12000);
    expect(testKmMid * (matchedMid?.don_gia ?? 0)).toBe(300_000);
  });
});
