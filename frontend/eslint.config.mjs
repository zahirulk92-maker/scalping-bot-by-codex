import { FlatCompat } from "@eslint/eslintrc";
import { globalIgnores } from "eslint/config";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });
const config = [
  globalIgnores([".next/**", "next-env.d.ts", "eslint.config.mjs", "postcss.config.mjs"]),
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];

export default config;
