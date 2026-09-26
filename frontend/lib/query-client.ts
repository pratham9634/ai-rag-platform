import { QueryClient } from "@tanstack/react-query";

/**
 * Global TanStack Query Client configuration.
 *
 * Configures optimal caching, garbage collection, and window-focus
 * revalidation policies for enterprise multi-tenant workloads.
 */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 10 * 1000, // 10 seconds fresh window
        gcTime: 5 * 60 * 1000, // 5 minutes cache retention
        refetchOnWindowFocus: true,
        refetchOnReconnect: true,
        retry: (failureCount, error) => {
          // Do not retry 4xx client errors
          if (error instanceof Error && error.message.includes("40")) {
            return false;
          }
          return failureCount < 2;
        },
      },
    },
  });
}

let browserQueryClient: QueryClient | undefined = undefined;

export function getQueryClient(): QueryClient {
  if (typeof window === "undefined") {
    // Server: always create a new query client
    return makeQueryClient();
  } else {
    // Browser: create once and reuse across component lifecycles
    if (!browserQueryClient) browserQueryClient = makeQueryClient();
    return browserQueryClient;
  }
}
