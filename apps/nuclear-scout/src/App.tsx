import { useState } from "react";
import "./App.css";

type Article = {
  title: string;
  link: string;
  published: string;
};

function App() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(false);

  const loadArticles = async () => {
    setLoading(true);

    const response = await fetch("http://127.0.0.1:8000/api/v1/articles");
    const data = await response.json();

    setArticles(data);
    setLoading(false);
  };

  return (
    <div className="app">
      <div className="container">
        <div className="logo">🌍</div>

        <h1>Nuclear Scout</h1>

        <h2>
          Discovering Changes
          <br />
          in the Global Nuclear Industry
        </h2>

        <p>AI-powered Research Platform</p>

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
              <strong>{article.title}</strong>
              <span>{article.published}</span>
            </a>
          ))}
        </div>

        <span className="version">Version 0.0.1 Alpha</span>
      </div>
    </div>
  );
}

export default App;