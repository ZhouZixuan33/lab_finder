import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { getProfessors, getTags } from "../api/client";
import Pagination from "../components/Pagination";
import ProfessorTable from "../components/ProfessorTable";
import StatusFilter from "../components/StatusFilter";
import TagFilter from "../components/TagFilter";

const PAGE_SIZE = 25;

function selectedTags(searchParams) {
  return (searchParams.get("tags") ?? "").split(",").filter(Boolean);
}

export default function ProfessorListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchDraft, setSearchDraft] = useState(searchParams.get("q") ?? "");
  const [professors, setProfessors] = useState([]);
  const [tags, setTags] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, pages: 0, total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const queryString = searchParams.toString();
  const state = searchParams.get("state") ?? "";
  const page = Math.max(Number(searchParams.get("page")) || 1, 1);
  const activeTags = selectedTags(searchParams);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    Promise.all([
      getProfessors({ q: searchParams.get("q") ?? "", tags: searchParams.get("tags") ?? "", state, page, page_size: PAGE_SIZE }, { signal: controller.signal }),
      getTags({ signal: controller.signal }),
    ]).then(([catalog, tagResponse]) => {
      setProfessors(catalog.items);
      setPagination(catalog.pagination);
      setTags(tagResponse.items);
    }).catch((requestError) => {
      if (requestError.name !== "AbortError") setError(requestError.message);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [queryString]); // eslint-disable-line react-hooks/exhaustive-deps

  function updateQuery(updates) {
    const next = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key));
    setSearchParams(next);
  }

  function submitSearch(event) {
    event.preventDefault();
    updateQuery({ q: searchDraft.trim(), page: "" });
  }

  function clearFilters() {
    setSearchDraft("");
    setSearchParams({});
  }

  const hasFilters = Boolean(searchParams.get("q") || state || activeTags.length);
  return (
    <main className="main-content">
      <section className="page-heading">
        <div>
          <p className="eyebrow">UIUC ECE</p>
          <h1>Professors</h1>
          <p>Explore research interests and keep every lab application in one place.</p>
        </div>
      </section>

      <section className="filter-panel" aria-label="Professor filters">
        <form className="search-form" role="search" onSubmit={submitSearch}>
          <label className="field field--grow">
            <span>Search professors</span>
            <input type="search" value={searchDraft} placeholder="Name, title, research, or tag" onChange={(event) => setSearchDraft(event.target.value)} />
          </label>
          <button className="button button--primary" type="submit">Search</button>
        </form>
        <StatusFilter value={state} onChange={(value) => updateQuery({ state: value, page: "" })} />
        <TagFilter tags={tags} selected={activeTags} onChange={(values) => updateQuery({ tags: values.join(","), page: "" })} />
        {hasFilters && <button className="text-button" type="button" onClick={clearFilters}>Clear all filters</button>}
      </section>

      <section aria-live="polite" aria-busy={loading}>
        {loading && <div className="state-panel"><span className="spinner" aria-hidden="true" /> Loading professors…</div>}
        {!loading && error && <div className="state-panel state-panel--error" role="alert"><strong>Could not load professors.</strong><span>{error}</span></div>}
        {!loading && !error && professors.length === 0 && (
          <div className="state-panel"><strong>No professors found.</strong><span>{hasFilters ? "Try changing or clearing the filters." : "Use Find new professors to build your catalog."}</span></div>
        )}
        {!loading && !error && professors.length > 0 && <ProfessorTable professors={professors} />}
      </section>

      {!loading && !error && <Pagination page={pagination.page} pages={pagination.pages} total={pagination.total} onPageChange={(nextPage) => updateQuery({ page: String(nextPage) })} />}
    </main>
  );
}

