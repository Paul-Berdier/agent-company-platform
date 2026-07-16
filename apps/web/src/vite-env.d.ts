/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ACP_API_URL?: string;
  readonly VITE_ACP_EVENTS_WS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
