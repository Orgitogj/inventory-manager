import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { CSRF_HEADER } from "@/lib/api/client";
import {
  createFetchMock,
  errorResponse,
  jsonResponse,
  requestsTo,
  type Handler,
} from "@/test/fetch-mock";
import { SESSION } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { routerMock } from "@/test/router";

import { formatWait, LoginForm } from "./login-form";

const LOGIN_PATH = "/api/v1/auth/login";
const EMAIL = "ana@example.com";
const PASSWORD = "example-password";

function renderLogin(loginHandler: Handler) {
  const fetchMock = createFetchMock({
    "GET /api/v1/auth/me": () =>
      errorResponse(401, "unauthenticated", "Login required."),
    [`POST ${LOGIN_PATH}`]: loginHandler,
  });

  renderWithProviders(<LoginForm />, fetchMock);

  return fetchMock;
}

async function submit(email = EMAIL, password = PASSWORD) {
  const user = userEvent.setup();

  if (email !== "") {
    await user.type(screen.getByLabelText("Email"), email);
  }

  if (password !== "") {
    await user.type(screen.getByLabelText("Password"), password);
  }

  await user.click(screen.getByRole("button", { name: "Log in" }));
}

describe("LoginForm", () => {
  test("sends the credentials and goes to products on success", async () => {
    const fetchMock = renderLogin(() => jsonResponse(SESSION));

    await submit();

    await waitFor(() =>
      expect(routerMock.replace).toHaveBeenCalledWith("/products"),
    );

    const [request] = requestsTo(fetchMock, LOGIN_PATH);

    expect(await request.json()).toEqual({ email: EMAIL, password: PASSWORD });
    expect(request.headers.has(CSRF_HEADER)).toBe(false);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("shows the backend message for invalid credentials", async () => {
    renderLogin(() =>
      errorResponse(401, "invalid_credentials", "Invalid email or password."),
    );

    await submit();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid email or password.",
    );
    expect(screen.getByRole("button", { name: "Log in" })).toBeEnabled();
    expect(routerMock.replace).not.toHaveBeenCalledWith("/products");
  });

  test("shows the wait time when there are too many attempts", async () => {
    renderLogin(() =>
      errorResponse(
        429,
        "too_many_attempts",
        "Too many failed login attempts. Try again later.",
        { "Retry-After": "900" },
      ),
    );

    await submit();

    const alert = await screen.findByRole("alert");

    expect(alert).toHaveTextContent(
      "Too many failed login attempts. Try again later.",
    );
    expect(alert).toHaveTextContent("Try again in 15 minutes.");
  });

  test("shows field errors from a validation response", async () => {
    renderLogin(() =>
      errorResponse(422, "validation_error", "Invalid input.", {}, [
        { field: "email", message: "Enter a valid email address." },
        { field: "password", message: "Password is required." },
      ]),
    );

    await submit();

    expect(
      await screen.findByText("Enter a valid email address."),
    ).toBeInTheDocument();
    expect(screen.getByText("Password is required.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription(
      "Enter a valid email address.",
    );
    expect(screen.getByLabelText("Email")).toBeInvalid();
    expect(screen.getByLabelText("Password")).toBeInvalid();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("shows the backend message for an empty form", async () => {
    renderLogin(() =>
      errorResponse(400, "invalid_request", "Email and password are required."),
    );

    await submit("", "");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Email and password are required.",
    );
  });

  test("disables the button while submitting", async () => {
    let finish: (response: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => {
      finish = resolve;
    });

    renderLogin(() => pending);

    await submit();

    const button = screen.getByRole("button", { name: "Logging in…" });

    expect(button).toBeDisabled();

    finish(jsonResponse(SESSION));

    await waitFor(() =>
      expect(routerMock.replace).toHaveBeenCalledWith("/products"),
    );
  });

  test("shows a generic message when the request cannot be sent", async () => {
    renderLogin(() => {
      throw new TypeError("fetch failed");
    });

    await submit();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Something went wrong. Please try again.",
    );
    expect(screen.getByRole("button", { name: "Log in" })).toBeEnabled();
  });
});

describe("formatWait", () => {
  test.each([
    [1, "1 second"],
    [45, "45 seconds"],
    [60, "1 minute"],
    [61, "2 minutes"],
    [900, "15 minutes"],
  ])("%i seconds is shown as %s", (seconds, expected) => {
    expect(formatWait(seconds)).toBe(expected);
  });
});
