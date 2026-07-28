"use client";

import { CHOICES, QUESTIONS } from "@/lib/questionnaire";

/**
 * Eight preference questions. Answering none is valid — every unanswered
 * question stays neutral and contributes nothing to the score, which the copy
 * says so nobody feels obliged to guess.
 */
export function Questionnaire({
  answers,
  onChange,
}: {
  answers: Record<string, number>;
  onChange: (next: Record<string, number>) => void;
}) {
  const answered = Object.keys(answers).length;

  return (
    <div>
      <p className="lead" style={{ fontSize: 14 }}>
        Answer what you have an opinion about — skipping a question just means it
        won&rsquo;t count. {answered} of {QUESTIONS.length} answered.
      </p>

      {QUESTIONS.map((question) => (
        <fieldset
          key={question.id}
          style={{ border: 0, padding: 0, margin: "0 0 20px" }}
        >
          <legend style={{ fontSize: 14, fontWeight: 650, marginBottom: 8 }}>
            {question.prompt}
          </legend>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            {CHOICES.map((choice) => {
              const selected = answers[question.id] === choice;
              return (
                <button
                  key={choice}
                  type="button"
                  aria-label={`${question.prompt} — ${
                    choice < 0.5 ? question.low : choice > 0.5 ? question.high : "no preference"
                  }`}
                  aria-pressed={selected}
                  className={`chip ${selected ? "on" : ""}`}
                  style={{ flex: 1, textAlign: "center" }}
                  onClick={() => {
                    const next = { ...answers };
                    if (selected) delete next[question.id];
                    else next[question.id] = choice;
                    onChange(next);
                  }}
                >
                  {choice === 0.5 ? "either" : choice === 0 || choice === 1 ? "●" : "○"}
                </button>
              );
            })}
          </div>
          <div className="slider-ends">
            <span>{question.low}</span>
            <span>{question.high}</span>
          </div>
        </fieldset>
      ))}
    </div>
  );
}
