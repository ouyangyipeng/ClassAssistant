# 课狐 ClassFox 文档分支

这个 docs 分支专门用于项目文档和 GitHub Pages 发布。

它的目标很明确：

- 保留 MkDocs Material 文档源文件
- 保留 GitHub Pages 可直接发布的静态站点文件
- 不再保留应用源码、构建脚本、运行时数据或发布包

## GitHub Pages 设置

在仓库 Settings -> Pages 中选择：

- Branch: docs
- Folder: /(root)

这样 GitHub Pages 会直接把本分支根目录下的静态页面作为站点内容发布。

## 分支结构

- docs/: Markdown 文档源文件与图片素材
- mkdocs.yml: MkDocs Material 站点配置
- requirements-docs.txt: 文档构建依赖
- 根目录 index.html、assets/、search/ 等: 已生成的发布文件
- .nojekyll: 防止 GitHub Pages 误处理静态资源

## 本地预览

```powershell
python -m venv .venv-docs
.venv-docs\Scripts\pip install -r requirements-docs.txt
.venv-docs\Scripts\mkdocs serve
```

默认预览地址：[http://127.0.0.1:8000](http://127.0.0.1:8000)

## 重新生成用于 GitHub Pages 的根目录静态站点

```powershell
.venv-docs\Scripts\mkdocs build -d pages-dist
```

生成后，把 pages-dist 的内容覆盖到分支根目录即可。

## 维护约定

- 文档源码统一维护在 docs/
- 发布内容统一维护在分支根目录
- 这个分支不再合并应用代码目录
