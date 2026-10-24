/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_USE_MOCKS?: string;
  readonly VITE_BOUNTY_EMAIL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
