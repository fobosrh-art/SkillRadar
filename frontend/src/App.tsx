import { Link, Route, Routes, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Layout } from "./components/Layout";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Empty } from "./components/ui";
import Overview from "./pages/Overview";
import Jobs from "./pages/Jobs";
import Skills from "./pages/Skills";
import Career from "./pages/Career";
import Roadmap from "./pages/Roadmap";
import Salary from "./pages/Salary";
import Pipeline from "./pages/Pipeline";
import Quality from "./pages/Quality";
import Sources from "./pages/Sources";
import Operations from "./pages/Operations";

export default function App() {
  const { t } = useTranslation();
  const loc = useLocation();
  return (
    <Layout>
      {/* keyed by route: a render error stays on its page and is cleared by navigating away */}
      <ErrorBoundary key={loc.pathname} fallback={(e, reset) => (
        <div className="card"><Empty title={t("common.pageError")}>
          {t("common.pageErrorHint", { msg: e.message })}
          <div className="mt-3"><button className="btn-secondary" onClick={reset}>{t("common.tryAgain")}</button></div>
        </Empty></div>
      )}>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/skills" element={<Skills />} />
          <Route path="/career" element={<Career />} />
          <Route path="/roadmap" element={<Roadmap />} />
          <Route path="/salary" element={<Salary />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/quality" element={<Quality />} />
          <Route path="/sources" element={<Sources />} />
          <Route path="/operations" element={<Operations />} />
          <Route path="*" element={<div className="card"><Empty title={t("common.notFound")}><Link className="text-indigo-700" to="/">{t("common.backHome")}</Link></Empty></div>} />
        </Routes>
      </ErrorBoundary>
    </Layout>
  );
}
