export type ApiErrorDetail = {
  field: string;
  message: string;
};

type ApiErrorOptions = {
  status: number;
  code: string;
  message: string;
  details?: ApiErrorDetail[];
  retryAfterSeconds?: number | null;
};

export const UNKNOWN_ERROR_CODE = "unknown_error";
export const UNKNOWN_ERROR_MESSAGE = "Something went wrong. Please try again.";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ApiErrorDetail[] | undefined;
  readonly retryAfterSeconds: number | null;

  constructor(options: ApiErrorOptions) {
    super(options.message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.details = options.details;
    this.retryAfterSeconds = options.retryAfterSeconds ?? null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseDetails(value: unknown): ApiErrorDetail[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }

  return value.flatMap((item) =>
    isRecord(item) &&
    typeof item.field === "string" &&
    typeof item.message === "string"
      ? [{ field: item.field, message: item.message }]
      : [],
  );
}

function parseRetryAfter(value: string | null): number | null {
  if (value === null || !/^\d+$/.test(value.trim())) {
    return null;
  }

  return Number(value.trim());
}

export async function toApiError(response: Response): Promise<ApiError> {
  const retryAfterSeconds = parseRetryAfter(
    response.headers.get("Retry-After"),
  );
  const body: unknown = await response.json().catch(() => null);
  const error = isRecord(body) ? body.error : null;

  if (
    !isRecord(error) ||
    typeof error.code !== "string" ||
    typeof error.message !== "string"
  ) {
    return new ApiError({
      status: response.status,
      code: UNKNOWN_ERROR_CODE,
      message: UNKNOWN_ERROR_MESSAGE,
      retryAfterSeconds,
    });
  }

  return new ApiError({
    status: response.status,
    code: error.code,
    message: error.message,
    details: parseDetails(error.details),
    retryAfterSeconds,
  });
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : UNKNOWN_ERROR_MESSAGE;
}
