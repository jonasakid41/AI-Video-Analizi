import { describe, expect, it } from "vitest";
import { Mapping, fmtClock, fmtMedia, fmtOffset, isoToSec, secToIso } from "./time";

const BASE = isoToSec("2026-10-28T14:30:00");

describe("Mapping (motorla aynı sonuçlar)", () => {
  it("tek referans: sabit fark", () => {
    const m = new Mapping({
      pieces: [{ t_from: 0, offset: BASE }],
      corrections: [["2026-10-28T14:30:00", "2026-10-28T14:26:18"]],
      tz: "Europe/Istanbul",
      source: "elle",
      gaps: [],
    });
    expect(m.realSec(60)).toBeCloseTo(BASE + 60 - 222);
    expect(secToIso(m.realSec(60)!)).toBe("2026-10-28T14:27:18");
  });

  it("iki referans: günlük kayma", () => {
    const m = new Mapping({
      pieces: [{ t_from: 0, offset: BASE }],
      corrections: [
        ["2026-10-28T14:30:00", "2026-10-28T14:30:00"],
        ["2026-10-29T14:30:00", "2026-10-29T14:30:02"],
      ],
      tz: "",
      source: "elle",
      gaps: [],
    });
    expect(m.realSec(43200)).toBeCloseTo(BASE + 43201, 3);
  });

  it("kayıt boşluğu: parçalar", () => {
    const m = new Mapping({ pieces: [{ t_from: 0, offset: BASE }, { t_from: 10, offset: BASE + 600 }], corrections: [], tz: "", source: "osd", gaps: [] });
    expect(m.cameraSec(5)).toBe(BASE + 5);
    expect(m.cameraSec(12)).toBe(BASE + 612);
  });

  it("gerçek saatten video zamanına (ters dönüşüm)", () => {
    const m = new Mapping({
      pieces: [{ t_from: 0, offset: BASE }, { t_from: 10, offset: BASE + 600 }],
      corrections: [["2026-10-28T14:30:00", "2026-10-28T14:26:18"]],
      tz: "", source: "osd", gaps: [],
    });
    expect(m.toMedia(m.realSec(4)!, 20)).toBeCloseTo(4);
    expect(m.toMedia(m.realSec(15)!, 20)).toBeCloseTo(15);
    expect(m.toMedia(m.realSec(4)! + 100, 20)).toBeNull(); // kayıt boşluğuna düşen an
    const sp = m.spans(20);
    expect(sp.length).toBe(2);
    expect(sp[1].r0 - sp[0].r1).toBeCloseTo(600); // iki parça arasında 10 dk kayıt yok
  });

  it("saat bilinmiyorsa null", () => {
    expect(new Mapping(null).realSec(5)).toBeNull();
  });
});

describe("biçimlendirme", () => {
  it("saat ve süre", () => {
    expect(fmtClock(BASE)).toBe("28.10.2026 14:30:00");
    expect(fmtClock(BASE, false)).toBe("14:30:00");
    expect(fmtMedia(3725.5)).toBe("1:02:05");
    expect(fmtMedia(65.25, true)).toBe("01:05.250");
    expect(fmtOffset(-222)).toBe("−3 dk 42 sn");
  });
});
