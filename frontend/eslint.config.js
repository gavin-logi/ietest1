// 变更记录: 20261125-1119 修正：ESLint 配置仅匹配 .vue，JS/TS 交由 Oxlint 检查
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'
import eslintConfigPrettier from 'eslint-config-prettier'
import globals from 'globals'

// 分工（以文件类型划分，避免两个工具重复或漏检）：
// - .js / .ts：由 Oxlint 负责（规则见 .oxlintrc.json）
// - .vue：由 ESLint 负责（模板与 <script> 的规则全部在这里生效）
const vueFiles = ['**/*.vue']

export default [
  // 1. 全局忽略目录（不进行 Lint 检查）
  {
    ignores: [
      '**/dist/**',
      '**/dist-ssr/**',
      '**/coverage/**',
      '**/node_modules/**',
      '**/.vite/**',
    ],
  },

  // 2. 基础 JavaScript 与 TypeScript 推荐规则
  { ...js.configs.recommended, files: vueFiles },
  ...tseslint.configs.recommended.map((config) => ({ ...config, files: vueFiles })),

  // 3. Vue 3 官方推荐规则（包含 essential + strongly-recommended + recommended）
  ...pluginVue.configs['flat/recommended'],

  // 4. 解析器与通用规则（确保 <script setup lang="ts"> 正常解析）
  {
    files: vueFiles,
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      // 业务代码只允许浏览器全局变量，误用 process 等 Node API 会被发现
      globals: {
        ...globals.browser,
      },
      parserOptions: {
        parser: tseslint.parser,
      },
    },
    rules: {
      // 关闭组件名必须多个单词的限制（允许 Index.vue、Login.vue 等单字页面组件）
      'vue/multi-word-component-names': 'off',

      // 与 .oxlintrc.json 保持一致：any 只警告，不阻断提交
      '@typescript-eslint/no-explicit-any': 'warn',

      // 不再依赖 NODE_ENV：lint 时通常未设置该变量，原写法会让规则永远关闭
      'no-console': 'warn',
    },
  },

  // 5. 仅 .vue：生产代码禁止遗留 debugger，直接报错阻断；未使用变量统一为 warn
  {
    files: vueFiles,
    rules: {
      'no-debugger': 'error',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },

  // 6. 【关键】必须放在最后：关闭所有与 Prettier 冲突的 ESLint 排版规则
  eslintConfigPrettier,
]
