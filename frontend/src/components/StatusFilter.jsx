const OPTIONS = [
  ["", "All statuses"],
  ["interested", "Interested"],
  ["applied", "Applied"],
  ["accepted", "Accepted"],
  ["rejected", "Rejected"],
];

export default function StatusFilter({ value, onChange }) {
  return (
    <label className="field status-filter">
      <span>Application status</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {OPTIONS.map(([optionValue, label]) => (
          <option key={optionValue || "all"} value={optionValue}>{label}</option>
        ))}
      </select>
    </label>
  );
}

