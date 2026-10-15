import { describe, expect, it } from "vitest";
import { DECISION_LABEL, KIND_LABEL, taskLabel } from "./corpusV2";

describe("corpus v2 labels", () => {
  /** An unlabelled kind renders as an empty heading, so every kind must have one. */
  it("labels every claim kind the API can return", () => {
    const kinds = [
      "RESULT", "TRAINING", "TRAINING_EXTRA", "METHOD", "DATASET",
      "LIMITATION", "CONFLICT", "EXCLUSION", "OTHER",
    ] as const;
    for (const kind of kinds) {
      expect(KIND_LABEL[kind], kind).toBeTruthy();
    }
  });

  it("labels every audit state shown back to the auditor", () => {
    for (const state of ["ACCEPTED", "NEEDS_FIX", "REJECTED", "UNAUDITED", "STALE"]) {
      expect(DECISION_LABEL[state], state).toBeTruthy();
    }
  });

  it("keeps an unknown task readable instead of blank", () => {
    expect(taskLabel("FORECASTING")).toBe("Prévision");
    expect(taskLabel("SOMETHING_NEW")).toBe("SOMETHING_NEW");
  });
});
