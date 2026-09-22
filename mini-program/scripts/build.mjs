import { build } from "esbuild";
import { mkdir, readFile, copyFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(root, "src"),
  output = path.join(root, "dist");
const options = {
  bundle: true,
  platform: "neutral",
  format: "cjs",
  target: "es2020",
  minify: true,
  sourcemap: false,
  legalComments: "eof",
  logLevel: "info",
};
await mkdir(output, { recursive: true });
await build({
  ...options,
  entryPoints: [path.join(source, "runtime.ts")],
  outfile: path.join(output, "runtime.js"),
});
await build({
  ...options,
  entryPoints: [path.join(source, "app.ts")],
  external: ["./runtime"],
  outfile: path.join(output, "app.js"),
});
for (const file of ["app.json", "app.wxss", "sitemap.json"])
  await copyFile(path.join(source, file), path.join(output, file));
const pages = {
  classroom: "registerClassroom",
  history: "registerHistory",
  settings: "registerSettings",
};
for (const [name, register] of Object.entries(pages)) {
  const directory = path.join(output, "pages", name);
  await mkdir(directory, { recursive: true });
  for (const extension of ["wxml", "wxss"])
    await copyFile(
      path.join(source, "pages", name, `index.${extension}`),
      path.join(directory, `index.${extension}`),
    );
  await writeFile(
    path.join(directory, "index.js"),
    `require("../../runtime.js").${register}();\n`,
  );
  await writeFile(
    path.join(directory, "index.json"),
    '{"usingComponents":{"privacy-consent":"/components/privacy/index"}}\n',
  );
}
const component = path.join(output, "components", "privacy");
await mkdir(component, { recursive: true });
for (const extension of ["wxml", "wxss"])
  await copyFile(
    path.join(source, "components", "privacy", `index.${extension}`),
    path.join(component, `index.${extension}`),
  );
await writeFile(
  path.join(component, "index.js"),
  'require("../../runtime.js").registerPrivacy();\n',
);
await writeFile(
  path.join(component, "index.json"),
  '{"component":true,"usingComponents":{}}\n',
);
const packageInfo = JSON.parse(
  await readFile(path.join(root, "package.json"), "utf8"),
);
await writeFile(
  path.join(output, "version.json"),
  JSON.stringify({ version: packageInfo.version }) + "\n",
);
const licenses = [];
for (const dependency of Object.keys(packageInfo.dependencies)) {
  licenses.push(
    `${dependency}\n${await readFile(path.join(root, "node_modules", dependency, "LICENSE"), "utf8")}`,
  );
}
await writeFile(
  path.join(output, "THIRD_PARTY_LICENSES.txt"),
  licenses.join("\n\n"),
);
