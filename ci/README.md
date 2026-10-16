# CI 模板：等待 workflow 授权

`check.yml` 已配置 Node 22/24、Python 3.12、锁定的官方 Actions 版本，以及便携逻辑/桥接/安装回滚/打包检查。它目前放在 `ci/`，**不会被 GitHub Actions 自动执行**。

原因：发布时现有 GitHub CLI OAuth 令牌不含 `workflow` scope，GitHub 拒绝包含 `.github/workflows/check.yml` 的 push。没有为绕过该限制创建新令牌或扩大授权。

仓库所有者确认授权后执行：

```sh
gh auth refresh -h github.com -s workflow
mkdir -p .github/workflows
cp ci/check.yml .github/workflows/check.yml
git add .github/workflows/check.yml
git commit -m "ci: 启用便携测试"
git push origin main
```

完成 GitHub 官方授权页面的确认后，最后的 push 才能成功。随后必须在 Actions 中回读真实运行结果；模板存在不等于 CI 已通过。

原生窗口测试需要有 Tern 的 macOS 桌面，不能由此 Linux 工作流替代。
