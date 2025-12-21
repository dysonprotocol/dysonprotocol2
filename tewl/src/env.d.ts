/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

interface ImportMetaEnv {
  readonly VITE_TEWL_SCRIPT?: string;
  readonly VITE_DYSONPROTOCOL_API?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
