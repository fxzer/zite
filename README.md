<p align="center">English | <a href="README.zh-CN.md">中文</a></p>

<div align="center">
  <img src="crates/wu/resources/app-icon.png" alt="Zed Lite" width="128">
  <h1>Zed Lite</h1>
  <p>The ultra-fast, clean, and lightweight native code editor.</p>
  <p>Built on Zed's core architecture · Zero AI bloat · Pure editing experience</p>
</div>

---

**Zed Lite** is a high-performance native code editor written in Rust, focusing purely on speed, minimal memory footprint, and an uncompromised text editing experience. All bundled AI agents, speech dictation models, and heavy neural runtime dependencies have been completely stripped out, returning the editor to its core mission: blazing-fast, distraction-free code editing.

## 🌟 Key Custom Feature: Search Tree View

In stock Zed and traditional editors, multi-file search results are presented in a flat path list. In large monorepos with dozens of nested directories, this quickly becomes visually noisy and loses structural context.

Zed Lite introduces a seamless **dual-mode switcher** in the project search panel:

| Mode | Features |
| :--- | :--- |
| **Tree View** | Aggregates search hits into an interactive directory tree with foldable folders, indentation lines, high-fidelity file/directory icons, and hit counts per branch. |
| **Flat View** | Preserves the traditional compact list view for rapid single-file inspection. |

- **Instant Switching**: Toggle effortlessly via the `ListTree` button on the search toolbar.
- **Preference Persistence**: Your view mode choice is remembered across sessions.

---

## ⚡ Additional Highlights & Enhancements

### 1. Completely Detached AI Modules (~52k LOC Removed)
- Removed `agent_chat`, `agent_harness`, `dictation` (audio capture), and `mermaid_render`.
- Eliminated heavy C/C++ bindings such as ONNX Runtime (`ort`), `cpal`, and `rubato`.
- Full linking speed improved by ~40% - 60%, binary size reduced by 30 - 50MB, cold-start memory reduced by 30 - 80MB.
- Activity bar simplified to files, search, Git, and terminal.

### 2. Isolated Bundle ID & Coexistence with Official Zed
- Bundle ID: `dev.zed.Zed-Lite`, installed as `/Applications/Zed Lite.app`.
- Runs side-by-side with official `Zed.app` without configuration conflicts or cache collisions.
- Styled with a distinctive dark tech-focused app icon.

### 3. Absorbed Upstream Non-AI Enhancements
- **Sort by Extension**: Set `project_panel.sort_order = "extension"` to group files of the same type in the project tree.
- **Show Source in Markdown Preview**: Right-click the preview tab to return directly to markdown source.
- **Cmd+Q Crash Fix**: Integrated `minidump-writer` patch to eliminate macOS crash prompts on application quit.

### 4. Removed Silent Auto-Update Overwrites
- Neutralized the background poll-and-replace mechanism to ensure local modifications remain untouched.

---

## Building & Installation

### Requirements
- macOS 12.3+ (Apple Silicon / Intel)
- Rust stable toolchain

### Build and Install into /Applications
```sh
./script/bundle-mac -i
```

---

## Licensing & Acknowledgements

- Licensed under GPL-3.0-or-later and Apache-2.0.
- Built upon [Zed](https://github.com/zed-industries/zed) and GPUI.
