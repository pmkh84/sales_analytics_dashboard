import { useState } from "react";
import {
  ArrowRight,
  Lightbulb,
  LoaderCircle,
  Send,
  Sparkles,
} from "lucide-react";
import type { DateRange, Insight } from "../types";
import { askAI, errorMessage, getInsights } from "../services/api";
import { ErrorState } from "./States";
import { rangeLabel } from "../utils/format";

export function AIPanel({
  range,
  expanded = false,
}: {
  range: DateRange;
  expanded?: boolean;
}) {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [insightsError, setInsightsError] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [answerLoading, setAnswerLoading] = useState(false);
  const [answerError, setAnswerError] = useState("");
  async function generate() {
    setInsightsLoading(true);
    setInsightsError("");
    try {
      setInsights(await getInsights(range));
    } catch (error) {
      setInsightsError(errorMessage(error));
    } finally {
      setInsightsLoading(false);
    }
  }
  async function ask(value = question) {
    if (value.trim().length < 3 || answerLoading) return;
    setQuestion(value);
    setAnswerLoading(true);
    setAnswerError("");
    setAnswer("");
    try {
      setAnswer(await askAI(value.trim(), range));
    } catch (error) {
      setAnswerError(errorMessage(error));
    } finally {
      setAnswerLoading(false);
    }
  }
  return (
    <section className={"card ai-card " + (expanded ? "expanded" : "")}>
      <div className="card-heading">
        <div className="ai-heading">
          <span className="ai-symbol">
            <Sparkles size={20} />
          </span>
          <div>
            <h2>Your AI analyst</h2>
            <p>A little intelligence. A lot of clarity.</p>
          </div>
        </div>
        <span className="ai-badge">POWERED BY AI</span>
      </div>
      {insights.length > 0 ? (
        <div className="insights-list">
          {insights.map((insight, index) => (
            <div className="insight" key={index}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div>
                <h3>{insight.title}</h3>
                <p>{insight.detail}</p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="ai-intro">
          <Lightbulb size={22} />
          <div>
            <h3>Turn numbers into your next move.</h3>
            <p>
              Discover trends, standout categories, and opportunities in your
              sales data.
            </p>
          </div>
        </div>
      )}
      <button
        className="button ai-generate"
        onClick={generate}
        disabled={insightsLoading}
      >
        {insightsLoading ? (
          <LoaderCircle className="animate-spin" size={16} />
        ) : (
          <Sparkles size={16} />
        )}
        {insightsLoading ? "Analyzing your sales…" : "Generate AI Insights"}
        <ArrowRight size={16} />
      </button>
      {insightsError && <ErrorState message={insightsError} />}
      <div className="ask-section">
        <h3>Curious about something?</h3>
        <p>Ask a question about {rangeLabel(range)}.</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void ask();
          }}
        >
          <label className="sr-only" htmlFor="ai-question">
            Ask something about your sales data
          </label>
          <input
            id="ai-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask something about your sales data…"
            minLength={3}
            maxLength={1000}
            required
          />
          <button
            aria-label="Ask AI"
            title="Ask AI"
            disabled={answerLoading || question.trim().length < 3}
          >
            {answerLoading ? (
              <LoaderCircle className="animate-spin" size={17} />
            ) : (
              <Send size={17} />
            )}
          </button>
        </form>
        <div className="suggestions">
          {[
            "Which category performs best?",
            "What should I pay attention to?",
          ].map((value) => (
            <button
              key={value}
              disabled={answerLoading}
              onClick={() => void ask(value)}
            >
              {value}
            </button>
          ))}
        </div>
        {answerLoading && (
          <p role="status" className="thinking">
            Reviewing the selected sales data…
          </p>
        )}
        {answerError && <ErrorState message={answerError} />}
        {answer && (
          <div className="ai-answer" aria-live="polite">
            <span>
              <Sparkles size={15} /> Clarity AI
            </span>
            <p>{answer}</p>
          </div>
        )}
      </div>
      <div className="ai-footnote">
        Based on aggregated sales data. AI can make mistakes; verify important
        decisions.
      </div>
    </section>
  );
}
