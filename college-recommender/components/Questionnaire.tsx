"use client";

import { QUESTIONS } from "@/lib/questionnaire";

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

      {QUESTIONS.map((question) => {
        const value = answers[question.id];
        const choose = (next: number) => {
          const updated = { ...answers };
          if (updated[question.id] === next) delete updated[question.id];
          else updated[question.id] = next;
          onChange(updated);
        };
        return (
          <div key={question.id} className="qcard">
            <p className="qprompt">{question.prompt}</p>
            <div className="qhalves">
              <button
                type="button"
                className={`qhalf ${value !== undefined && value < 0.5 ? "on" : ""}`}
                aria-pressed={value !== undefined && value < 0.5}
                onClick={() => choose(0)}
              >
                {question.low}
              </button>
              <button
                type="button"
                className={`qeither ${value === 0.5 ? "on" : ""}`}
                aria-pressed={value === 0.5}
                onClick={() => choose(0.5)}
              >
                either
              </button>
              <button
                type="button"
                className={`qhalf ${value !== undefined && value > 0.5 ? "on" : ""}`}
                aria-pressed={value !== undefined && value > 0.5}
                onClick={() => choose(1)}
              >
                {question.high}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
