# 设计参考与许可说明

- [Tty7](https://github.com/l0ng-ai/tty7)，Apache-2.0：状态色 `#3B82F6 / #F59E0B / #22C55E`、等待 > 工作 > 结束的聚合规则、结束未读 pane 数字及小圆/空心圆形式。Luau 状态与展示实现重新编写；未复制 Rust 源码。
- [Tern Tab Status](https://github.com/yoyooyooo/tern-tab-status)，MIT，Copyright (c) 2026 Tern Tab Status contributors：参考其完整原生 pane ID 对照、Tern 原生标签 CSS 接入与保持手动颜色独立的思路。此实现不改写原生 tab.color，重写状态聚合、计数、布局与刷新管理。
- Dia 浏览器：用户提供的标签配色截图是整行底色和 hover 的视觉参考；未复制其图标、素材或源代码。
- Tern：Stencil Labs 的产品；本项目为独立插件，未修改 Tern 应用源码。

## Tern Tab Status 的 MIT 许可

MIT License

Copyright (c) 2026 Tern Tab Status contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
