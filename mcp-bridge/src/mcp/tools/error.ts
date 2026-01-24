import { ZodError } from "zod";

export type ToolError = {
  code: string;
  message: string;
  remediation?: string;
  details?: unknown;
};

export type NormalizedToolError = {
  error: ToolError;
  upstream?: unknown;
};

type ErrorWithPayload = { error?: ToolError };

export function normalizeToolError(err: unknown, remediation?: string): NormalizedToolError {
  if (err && typeof err === "object" && "error" in err) {
    const payload = (err as ErrorWithPayload).error;
    if (payload?.code && payload?.message) {
      return {
        error: {
          code: payload.code,
          message: payload.message,
          remediation: payload.remediation ?? remediation,
          details: payload.details,
        },
        upstream: err,
      };
    }
  }

  if (err instanceof ZodError) {
    return {
      error: {
        code: "invalid_input",
        message: "Invalid input.",
        remediation,
        details: err.flatten(),
      },
    };
  }

  const message = err instanceof Error ? err.message : String(err);
  return {
    error: {
      code: "unexpected_error",
      message,
      remediation,
    },
    upstream: err,
  };
}

export function formatToolErrorText(error: ToolError): string {
  if (!error.remediation) {
    return error.message;
  }
  return `${error.message} Remediation: ${error.remediation}`;
}
