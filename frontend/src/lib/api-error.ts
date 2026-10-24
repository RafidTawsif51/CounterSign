export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    message: string,
    /** The server's own message (detail or detail.error), without the method and path. */
    readonly detail: string = message,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
