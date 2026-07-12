/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL the frontend uses when calling the backend. Defaults to "/api"
   *  which the Vite dev proxy forwards to http://localhost:8000. In
   *  production set this to the deployed backend origin, e.g.
   *  "https://api.example.com" (no trailing slash). */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}