/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ACP_API_URL?: string;
  readonly VITE_ACP_EVENTS_WS_URL?: string;
  readonly VITE_ACP_DEV_GALLERY?: string;
  readonly VITE_ACP_LEGACY_OFFICE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
