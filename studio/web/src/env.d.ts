/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>
  export default component
}

// ant-design-vue v4 的 ESM 类型解析在 vue-tsc 下偶发找不到声明，这里兜底
declare module 'ant-design-vue'
