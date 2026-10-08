import js from '@eslint/js'
import globals from 'globals'
import hooks from 'eslint-plugin-react-hooks'
import refresh from 'eslint-plugin-react-refresh'
export default [{ignores:['dist','coverage']},{files:['**/*.{js,jsx}'],languageOptions:{ecmaVersion:2022,globals:globals.browser,parserOptions:{ecmaFeatures:{jsx:true},sourceType:'module'}},plugins:{'react-hooks':hooks,'react-refresh':refresh},rules:{...js.configs.recommended.rules,...hooks.configs.recommended.rules,...refresh.configs.vite.rules,'react-hooks/set-state-in-effect':'off','react-refresh/only-export-components':'off'}}]
