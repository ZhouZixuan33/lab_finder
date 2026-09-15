import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ProfessorTable from "./ProfessorTable";

test("shows Yes only for explicit prospective student evidence and otherwise leaves the cell empty", () => {
  render(<MemoryRouter><ProfessorTable professors={[
    { id: 1, name: "Alice", title: "Professor", tags: [], prospective_students_quote: "Please apply to join my group." },
    { id: 2, name: "Bob", title: "Professor", tags: [] },
  ]} /></MemoryRouter>);
  expect(screen.getByRole("columnheader", { name: "Prospective students" })).toBeInTheDocument();
  const rows = screen.getAllByRole("row");
  expect(within(rows[1]).getByText("Yes")).toHaveAttribute("title", "Please apply to join my group.");
  expect(rows[2].querySelector('[data-label="Prospective students"]')).toBeEmptyDOMElement();
});
