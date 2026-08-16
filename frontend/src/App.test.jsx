import { render, screen } from "@testing-library/react";

import App from "./App";


test("renders the application shell", () => {
  render(<App />);

  expect(screen.getByRole("banner")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Lab Application Tracker", level: 1 }),
  ).toBeInTheDocument();
  expect(screen.getByRole("main")).toBeInTheDocument();
});
