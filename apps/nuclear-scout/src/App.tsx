import { useEffect, useState } from "react";
import "./App.css";

type Analysis = {
  title: string;
  country: string;
  organization: string;
  technology: string;
  category: string;
  importance: number;
  summary: string;
  impact: string;
};

type Article = {
  title: string;
  link: string;
  published: string;
  event_key?: string;
  content_preview: string;
  analysis: Analysis;
};

type DashboardItem = {
  name: string;
  count: number;
  trend?: string;
};

type TopChange = {
  title: string;
  summary: string;
  display_summary_ko?: string;
  category: string;
  country: string;
  technology: string;
  importance: number;
  event_key: string;
};

type DailyDashboard = {
  today_changes: {
    policy: number;
    technology: number;
    investment: number;
    incident: number;
  };
  top_technologies: DashboardItem[];
  top_countries: DashboardItem[];
  top_changes: TopChange[];
};

const CHANGE_LABELS: Record<keyof DailyDashboard["today_changes"], string> = {
  policy: "정책",
  technology: "기술",
  investment: "투자",
  incident: "사고/이슈",
};

function App() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [dashboard, setDashboard] = useState<DailyDashboard | null>(null);
  const [loading, setLoading] = useState(false);

  const loadDashboard = async () => {
    try {
      const response = await fetch("http://127.0.0.1:8000/api/v1/dashboard/daily");

      if (!response.ok) {
        throw new Error("Failed to load daily dashboard.");
      }

      const data = await response.json();
      setDashboard(data);
    } catch (error) {
      console.error(error);
      setDashboard(null);
    }
  };

  const loadArticles = async () => {
    setLoading(true);

    try {
      const response = await fetch("http://127.0.0.1:8000/api/v1/articles");

      if (!response.ok) {
        throw new Error("Failed to load latest articles.");
      }

      const data = await response.json();

      setArticles(data);
      await loadDashboard();
    } catch (error) {
      console.error(error);
      alert("Failed to load articles.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDashboard();
  }, []);

  const totalArticles = articles.length;
  const analyzedArticles = articles.filter(
    (article) => article.analysis.category !== "Unknown"
  ).length;

  return (
    <div className="app">
      <div className="container">
        <div className="logo">NS</div>

        <h1>Nuclear Scout</h1>

        <h2>
          Discovering Changes
          <br />
          in the Global Nuclear Industry
        </h2>

        <div className="stats">
          <div>
            <strong>{totalArticles}</strong>
            <span>Articles</span>
          </div>
          <div>
            <strong>{analyzedArticles}</strong>
            <span>Analyzed</span>
          </div>
        </div>

        {dashboard && (
          <section className="dashboard" aria-label="Daily Change Dashboard">
            <div className="dashboard-header">
              <h3>Daily Change Dashboard</h3>
              <span>오늘의 원전 산업 변화 신호</span>
            </div>

            <div className="change-grid">
              {Object.entries(dashboard.today_changes).map(([name, count]) => (
                <div className="change-card" key={name}>
                  <span>{CHANGE_LABELS[name as keyof DailyDashboard["today_changes"]]}</span>
                  <strong>{count}</strong>
                </div>
              ))}
            </div>

            <div className="dashboard-columns">
              <div className="dashboard-panel">
                <h4>주목 기술</h4>
                <ul>
                  {dashboard.top_technologies.length > 0 ? (
                    dashboard.top_technologies.map((item) => (
                      <li key={item.name}>
                        <span>{item.name}</span>
                        <em>{item.trend === "up" ? "▲ " : ""}{item.count}</em>
                      </li>
                    ))
                  ) : (
                    <li>
                      <span>No signals yet</span>
                      <em>0</em>
                    </li>
                  )}
                </ul>
              </div>

              <div className="dashboard-panel">
                <h4>주요 국가</h4>
                <ul>
                  {dashboard.top_countries.length > 0 ? (
                    dashboard.top_countries.map((item) => (
                      <li key={item.name}>
                        <span>{item.name}</span>
                        <em>{item.count}</em>
                      </li>
                    ))
                  ) : (
                    <li>
                      <span>No signals yet</span>
                      <em>0</em>
                    </li>
                  )}
                </ul>
              </div>
            </div>

            <div className="top-changes">
              <h4>오늘의 핵심 변화 TOP 5</h4>
              <div>
                {dashboard.top_changes.length > 0 ? (
                  dashboard.top_changes.map((change) => (
                    <article key={change.event_key || change.title}>
                      <p>{change.display_summary_ko || change.summary}</p>
                      <span>
                        {change.country} · {change.technology} · {change.category} · Importance {change.importance}
                      </span>
                    </article>
                  ))
                ) : (
                  <article>
                    <p>No daily changes detected yet.</p>
                    <span>Load articles or refresh the backend collector.</span>
                  </article>
                )}
              </div>
            </div>
          </section>
        )}

        <button onClick={loadArticles}>
          {loading ? "Observing..." : "Load Latest Nuclear News"}
        </button>

        <div className="articles">
          {articles.map((article, index) => (
            <a
              className="article-card"
              href={article.link}
              target="_blank"
              rel="noreferrer"
              key={index}
            >
              <div className="article-top">
                <strong>{article.title}</strong>
                <em>Importance {article.analysis.importance}</em>
              </div>

              <p>{article.analysis.summary}</p>
              <p className="preview">{article.content_preview}</p>

              <div className="meta">
                <span>{article.analysis.country}</span>
                <span>{article.analysis.organization}</span>
                <span>{article.analysis.technology}</span>
                <span>{article.analysis.category}</span>
              </div>

              <small>{article.published}</small>
            </a>
          ))}
        </div>

        <span className="version">Version 0.0.1 Alpha</span>
      </div>
    </div>
  );
}

export default App;
