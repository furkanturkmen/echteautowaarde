"use client";

import { CornerDownLeft, Info, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { type AiAnswer, ApiError, askAboutValuation, fetchAiSuggestions } from "@/lib/api";

/**
 * Ask a question about this valuation.
 *
 * Deliberately not a chat interface. It sits last on the page, after all the
 * evidence, because the evidence is the product and this only explains it. One
 * question, one answer, in the same visual language as every other section —
 * no bubbles, no sparkles, no assistant persona.
 *
 * The example questions come from the backend, which offers only the ones the
 * stored valuation can actually answer.
 *
 * `grounded` covers the euro amounts and nothing else, so the wording here says
 * exactly that. A model can quote every figure correctly and still describe the
 * relationship between them wrongly, and "geverifieerd" would promise a check
 * this product does not perform.
 */

const MAX_QUESTION_LENGTH = 600;

type State =
  | { status: "idle" }
  | { status: "asking" }
  | { status: "answered"; result: AiAnswer }
  | { status: "failed"; message: string };

export function AskPanel({ valuationId }: { valuationId: number }) {
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<State>({ status: "idle" });
  const [suggestions, setSuggestions] = useState<string[]>([]);
  // Null while unknown: the controls stay hidden rather than flashing an
  // interface that cannot work.
  const [aiAvailable, setAiAvailable] = useState<boolean | null>(null);

  useEffect(() => {
    let active = true;
    fetchAiSuggestions(valuationId)
      .then((result) => {
        if (!active) return;
        setSuggestions(result.questions);
        setAiAvailable(result.available);
      })
      .catch(() => {
        if (active) setAiAvailable(false);
      });
    return () => {
      active = false;
    };
  }, [valuationId]);

  async function ask(text: string) {
    const trimmed = text.trim();
    if (trimmed.length < 2) return;

    setState({ status: "asking" });
    try {
      const result = await askAboutValuation(valuationId, trimmed.slice(0, MAX_QUESTION_LENGTH));
      setState({ status: "answered", result });
      if (!result.available) setAiAvailable(false);
    } catch (caught) {
      setState({
        status: "failed",
        message:
          caught instanceof ApiError
            ? caught.message
            : "De vraag kon niet worden verstuurd. Probeer het opnieuw.",
      });
    }
  }

  const unavailable = aiAvailable === false;

  return (
    <section aria-labelledby="uitleg-titel" className="mt-12">
      <h2 id="uitleg-titel" className="text-lg font-semibold text-ink">
        Vraag het aan Echte Auto Waarde
      </h2>
      <p className="mt-1 text-sm text-muted">
        Stel een vraag over deze waardering. De antwoorden zijn gebaseerd op de gegevens
        hierboven.
      </p>

      <div className="mt-5 rounded-eaw-lg border border-line bg-surface p-6 sm:p-8">
        {unavailable ? (
          <div className="flex gap-3">
            <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted" strokeWidth={2} />
            <div>
              <p className="text-sm text-ink">
                {state.status === "answered" && state.result.unavailableReason
                  ? state.result.unavailableReason
                  : "AI-uitleg is lokaal niet beschikbaar. De waardering en vergelijkbare auto's blijven gewoon beschikbaar."}
              </p>
              <p className="mt-2 text-sm text-muted">
                De uitleg draait op een lokaal taalmodel. Start Ollama en installeer het
                ingestelde model om deze uitleg te gebruiken.
              </p>
            </div>
          </div>
        ) : (
          <>
            {suggestions.length > 0 && state.status === "idle" ? (
              <div>
                <p className="text-xs font-medium tracking-wide text-subtle uppercase">
                  Bijvoorbeeld
                </p>
                <ul className="mt-3 flex flex-wrap gap-2">
                  {suggestions.slice(0, 4).map((suggestion) => (
                    <li key={suggestion}>
                      <button
                        type="button"
                        onClick={() => {
                          setQuestion(suggestion);
                          void ask(suggestion);
                        }}
                        className="rounded-eaw border border-line bg-surface px-3 py-2 text-left text-sm text-ink transition-colors hover:border-line-strong hover:bg-surface-muted"
                      >
                        {suggestion}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <form
              onSubmit={(event) => {
                event.preventDefault();
                void ask(question);
              }}
              className={suggestions.length > 0 && state.status === "idle" ? "mt-6" : ""}
            >
              <label htmlFor="ai-vraag" className="block text-sm font-medium text-ink">
                Je vraag
              </label>
              <div className="mt-2 flex flex-col gap-3 sm:flex-row">
                <input
                  id="ai-vraag"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  maxLength={MAX_QUESTION_LENGTH}
                  placeholder="Waarom ligt het prijsadvies onder de vraagprijs?"
                  autoComplete="off"
                  className="h-11 w-full rounded-eaw border border-line-strong bg-surface px-3 text-sm text-ink placeholder:text-subtle"
                />
                <Button
                  type="submit"
                  disabled={state.status === "asking" || question.trim().length < 2}
                  className="shrink-0"
                >
                  {state.status === "asking" ? "Bezig…" : "Vraag stellen"}
                  {state.status === "asking" ? null : (
                    <CornerDownLeft aria-hidden="true" className="size-4" />
                  )}
                </Button>
              </div>
            </form>

            <div aria-live="polite">
              {state.status === "asking" ? (
                <div className="mt-5 border-t border-line pt-5">
                  <p className="sr-only">Het antwoord wordt opgesteld.</p>
                  <div className="h-3 w-3/4 animate-pulse rounded bg-surface-muted" />
                  <div className="mt-2.5 h-3 w-2/3 animate-pulse rounded bg-surface-muted" />
                </div>
              ) : null}

              {state.status === "answered" && state.result.available && state.result.answer ? (
                <div className="mt-5 border-t border-line pt-5">
                  <p className="text-sm leading-[1.7] whitespace-pre-line text-ink">
                    {state.result.answer}
                  </p>

                  {!state.result.grounded && state.result.groundingNote ? (
                    <p className="mt-4 flex gap-2.5 rounded-eaw border border-caution/20 bg-caution-soft p-3 text-sm text-caution">
                      <TriangleAlert
                        aria-hidden="true"
                        className="mt-0.5 size-4 shrink-0"
                        strokeWidth={2}
                      />
                      {state.result.groundingNote}
                    </p>
                  ) : null}

                  <p className="mt-4 text-xs text-subtle">
                    Uitleg door een lokaal taalmodel ({state.result.model}) op basis van de
                    gegevens hierboven. De waardering zelf komt niet van dit model.
                    {state.result.grounded
                      ? " Bedragen gecontroleerd aan deze waardering; de uitleg zelf is niet gecontroleerd."
                      : null}
                  </p>
                </div>
              ) : null}

              {state.status === "failed" ? (
                <p role="alert" className="mt-5 border-t border-line pt-5 text-sm text-negative">
                  {state.message}
                </p>
              ) : null}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
