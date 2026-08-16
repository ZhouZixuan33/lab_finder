export default function TagFilter({ tags, selected, onChange }) {
  const selectedSet = new Set(selected);

  function toggle(tag) {
    onChange(selectedSet.has(tag) ? selected.filter((value) => value !== tag) : [...selected, tag]);
  }

  return (
    <fieldset className="tag-filter">
      <legend>Research tags</legend>
      <div className="tag-filter__options">
        {tags.map(({ tag, professor_count: count }) => (
          <label className="filter-chip" key={tag}>
            <input type="checkbox" checked={selectedSet.has(tag)} onChange={() => toggle(tag)} />
            <span>{tag}</span>
            <span className="filter-chip__count">{count}</span>
          </label>
        ))}
        {tags.length === 0 && <span className="muted">No tags yet</span>}
      </div>
    </fieldset>
  );
}

