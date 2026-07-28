/**
 * The whole point of the honest-nulls data model is that the UI shows the
 * difference. If a null renders as "0" or an empty cell, the design was
 * pointless and the user is misled.
 */
import { describe, expect, it } from "vitest";

import { formatStat, tierLabel } from "./format";

describe("formatStat", () => {
  it("renders an observed value plainly", () => {
    expect(formatStat(0.204, "observed", "percent")).toEqual({
      text: "20%",
      note: null,
    });
  });

  it("never renders a null as zero", () => {
    const rendered = formatStat(null, "absent", "percent");

    expect(rendered.text).not.toBe("0");
    expect(rendered.text).not.toBe("0%");
    expect(rendered.text).toBe("—");
  });

  it("distinguishes not_applicable from absent", () => {
    const notApplicable = formatStat(null, "not_applicable", "number");
    const absent = formatStat(null, "absent", "number");

    expect(notApplicable.text).not.toBe(absent.text);
    expect(notApplicable.text).toBe("n/a");
    expect(notApplicable.note).toMatch(/not (used|applicable)/i);
  });

  it("marks an editorial figure as an estimate", () => {
    expect(formatStat(30000, "editorial", "money").note).toMatch(/est/i);
  });

  it("treats a genuine zero as a value, not a gap", () => {
    // A free school (net price 0) must not render like missing data.
    const free = formatStat(0, "observed", "money");

    expect(free.text).toBe("$0");
    expect(free.text).not.toBe("—");
  });

  it("falls back to absent when provenance is missing", () => {
    expect(formatStat(null, undefined, "number").text).toBe("—");
  });

  it("formats money and numbers readably", () => {
    expect(formatStat(20111, "observed", "money").text).toBe("$20,111");
    expect(formatStat(34177, "observed", "number").text).toBe("34,177");
  });
});

describe("tierLabel", () => {
  it("labels each tier", () => {
    expect(tierLabel("reach")).toBe("Reach");
    expect(tierLabel("target")).toBe("Target");
    expect(tierLabel("safety")).toBe("Safety");
  });

  it("returns null when there is no tier to show", () => {
    expect(tierLabel(null)).toBeNull();
    expect(tierLabel(undefined)).toBeNull();
  });
});

describe("formatStat decimals", () => {
  it("does not round a GPA to a whole number", () => {
    // 3.95 rendered as "4" would misstate how selective a school is.
    expect(formatStat(3.95, "editorial", "decimal").text).toBe("3.95");
  });

  it("keeps two decimal places consistently", () => {
    expect(formatStat(3.5, "editorial", "decimal").text).toBe("3.50");
  });
});

describe("formatStat score kind", () => {
  it("renders an SAT score without a thousands separator", () => {
    // "1,550" is not how anyone writes an SAT score.
    expect(formatStat(1550, "observed", "score").text).toBe("1550");
  });

  it("still separates thousands for counts like enrollment", () => {
    expect(formatStat(34177, "observed", "number").text).toBe("34,177");
  });
});
