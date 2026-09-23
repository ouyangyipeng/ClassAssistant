# 官网与品牌维护

ClassFox 产品主页由 `website/` 中的 HTML、CSS、JavaScript 和静态素材组成，无运行时框架或第三方跟踪脚本。设计使用暖白、炭黑和狐狸橙，所有颜色与字体在 `website/assets/site.css` 的变量中定义。

## 构建与预览

```bash
uv sync --project api-service --locked --only-group docs
uv run --project api-service --no-sync zensical build --strict
cp -R website/. site/
python3 -m http.server 8080 --directory site
```

产品主页覆盖生成目录的根 `index.html`，技术文档保留在原有的 `user-guide/`、`getting-started/`、`project/` 与 `developer/` 路径；文档入口为 `/guide/`。`site/` 是构建产物，不提交到 Git。只预览宣传页时可直接用 HTTP server 服务 `website/`，此时技术文档链接尚不可用。

GitHub Pages 使用 `.github/workflows/docs.yml` 构建，手动执行 `deploy=true` 后部署 `main`。仓库 Pages 自定义域名为 `class.nexa-lang.com`；阿里云主机记录 `class` 使用 CNAME 指向 `ouyangyipeng.github.io`，不能在记录值中填写协议或路径。HTTPS 由 GitHub Pages 签发，DNS 配置成功和 HTTPS 可用分别验证。

## 素材

- 品牌源文件与来源说明位于 `assets/brand/`；旧狐狸素材保留在 `docs/img/`。
- 平台图标由 Tauri CLI 从同一方形主图生成；应用界面直接引用生成后的图标。
- `classroom.png`、`notes.png`、`compact.png` 来自真实应用界面的浏览器回归场景，使用临时数据库与合成模型响应。更新应用后可运行 `pnpm --dir app-ui test:e2e` 并从 `app-ui/test-results/` 复制对应图片。
- 声波丝带插图是生成的概念视觉，不是产品截图。网页使用压缩 JPEG，README 共用网页素材。

发布新补丁时同步三平台下载链接、版本文案与安装包名称。不要覆盖旧 Release 资产，也不要把尚未完成的功能写成正式交付。

## 验证

检查桌面和手机布局、横向溢出、预览标签键盘导航、无 JavaScript 基本可用性、减少动态效果偏好、FAQ 展开、下载和文档链接。截图与插图都有说明及替代文本。DNS 变更仅针对 `class`，保留其他记录和历史分支。
