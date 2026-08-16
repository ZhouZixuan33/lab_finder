export default function Pagination({ page, pages, total, onPageChange }) {
  if (total === 0) return null;
  return (
    <nav className="pagination" aria-label="Professor list pagination">
      <button className="button button--secondary" type="button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Previous</button>
      <span>Page <strong>{page}</strong> of <strong>{Math.max(pages, 1)}</strong><span className="pagination__total"> · {total} professors</span></span>
      <button className="button button--secondary" type="button" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>Next</button>
    </nav>
  );
}
