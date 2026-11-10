use std::path::PathBuf;
use std::time::Duration;

use gpui::{
    App, ClipboardItem, Context, Empty, EventEmitter, IntoElement, ParentElement, Render,
    SharedString, Task, WeakEntity, Window,
};
use i18n::t;
use settings::Settings;
use ui::{Button, Icon, IconName, LabelSize, Tooltip, prelude::*};
use util::paths::PathStyle;

use project::Project;

use crate::{
    HideStatusItem, StatusItemView, item::ItemHandle,
    workspace_settings::StatusBarSettings,
};

pub struct ActiveFileName {
    project: Option<WeakEntity<Project>>,
    project_path: Option<SharedString>,
    full_path: Option<SharedString>,
    abs_path: Option<PathBuf>,
    copied: bool,
    _copy_task: Option<Task<()>>,
}

impl ActiveFileName {
    pub fn new(project: Option<WeakEntity<Project>>) -> Self {
        Self {
            project,
            project_path: None,
            full_path: None,
            abs_path: None,
            copied: false,
            _copy_task: None,
        }
    }

    fn copy_to_clipboard(&mut self, cx: &mut Context<Self>) {
        let text_to_copy = if let Some(abs_path) = self.abs_path.as_ref() {
            abs_path.to_string_lossy().to_string()
        } else if let Some(full_path) = self.full_path.as_ref() {
            full_path.to_string()
        } else if let Some(project_path) = self.project_path.as_ref() {
            project_path.to_string()
        } else {
            return;
        };

        cx.write_to_clipboard(ClipboardItem::new_string(text_to_copy));
        self.copied = true;
        cx.notify();

        self._copy_task = Some(cx.spawn(async move |this, cx| {
            cx.background_executor()
                .timer(Duration::from_millis(1800))
                .await;
            this.update(cx, |this, cx| {
                this.copied = false;
                cx.notify();
            })
            .ok();
        }));
    }
}

impl Render for ActiveFileName {
    fn render(&mut self, _window: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        if !StatusBarSettings::get_global(cx).show_active_file {
            return Empty.into_any_element();
        }

        let Some(project_path) = self.project_path.clone() else {
            return Empty.into_any_element();
        };

        let tooltip_text = if self.copied {
            t!("Copied")
        } else if let Some(abs_path) = self.abs_path.as_ref() {
            SharedString::from(format!("{}\n{}", t!("Copy Path"), abs_path.display()))
        } else if let Some(full_path) = self.full_path.as_ref() {
            SharedString::from(format!("{}\n{}", t!("Copy Path"), full_path))
        } else {
            project_path.clone()
        };

        let mut button = Button::new("active-file-name-button", project_path)
            .label_size(LabelSize::Small)
            .tooltip(Tooltip::text(tooltip_text))
            .on_click(cx.listener(|this, _, _, cx| {
                this.copy_to_clipboard(cx);
            }));

        if self.copied {
            button = button.end_icon(
                Icon::new(IconName::Check)
                    .color(Color::Success)
                    .size(IconSize::XSmall),
            );
        }

        div().child(button).into_any_element()
    }
}

impl EventEmitter<crate::ToolbarItemEvent> for ActiveFileName {}

impl StatusItemView for ActiveFileName {
    fn set_active_pane_item(
        &mut self,
        active_pane_item: Option<&dyn ItemHandle>,
        _window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        if let Some(item) = active_pane_item {
            let project_path = item.project_path(cx);
            self.project_path = project_path
                .as_ref()
                .map(|path| path.path.display(PathStyle::local()).into_owned().into());
            self.full_path = item.tab_tooltip_text(cx);

            let mut resolved_abs_path = None;
            if let Some(project_path) = project_path.as_ref()
                && let Some(project) = self.project.as_ref().and_then(|p| p.upgrade())
            {
                resolved_abs_path = project.read(cx).absolute_path(project_path, cx);
            }

            if resolved_abs_path.is_none()
                && let Some(full) = self.full_path.as_ref()
            {
                let path_str = full.as_ref();
                let target_str = if let Some((_, right)) = path_str.split_once(" ↔ ") {
                    right.trim()
                } else {
                    path_str.trim()
                };

                let expanded = if let Some(stripped) = target_str.strip_prefix("~/") {
                    dirs::home_dir().map(|h| h.join(stripped))
                } else if target_str.starts_with('/') {
                    Some(PathBuf::from(target_str))
                } else {
                    None
                };
                resolved_abs_path = expanded;
            }

            self.abs_path = resolved_abs_path;
        } else {
            self.project_path = None;
            self.full_path = None;
            self.abs_path = None;
            self.copied = false;
            self._copy_task = None;
        }
        cx.notify();
    }

    fn hide_setting(&self, _: &App) -> Option<HideStatusItem> {
        Some(HideStatusItem::new(|settings| {
            settings.status_bar.get_or_insert_default().show_active_file = Some(false);
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use gpui::TestAppContext;

    #[gpui::test]
    async fn test_active_file_name_copy_and_feedback(cx: &mut TestAppContext) {
        let active_file_name = cx.update(|cx| {
            let mut item = ActiveFileName::new(None);
            item.project_path = Some("src/test.rs".into());
            item.abs_path = Some(PathBuf::from("/Users/test/project/src/test.rs"));
            cx.new(|_| item)
        });

        // 初始状态未复制
        active_file_name.read_with(cx, |this, _| {
            assert!(!this.copied);
            assert_eq!(this.project_path.as_deref(), Some("src/test.rs"));
            assert_eq!(
                this.abs_path.as_deref(),
                Some(std::path::Path::new("/Users/test/project/src/test.rs"))
            );
        });

        // 触发点击复制
        active_file_name.update(cx, |this, cx| {
            this.copy_to_clipboard(cx);
            assert!(this.copied);
        });

        // 验证剪切板写入绝对路径
        cx.update(|cx| {
            assert_eq!(
                cx.read_from_clipboard().and_then(|item| item.text()),
                Some("/Users/test/project/src/test.rs".to_string())
            );
        });

        // 推进时钟 1850ms，微反馈图标自动恢复
        cx.background_executor.advance_clock(Duration::from_millis(1850));

        active_file_name.read_with(cx, |this, _| {
            assert!(!this.copied, "copied feedback icon should disappear after timer expires");
        });
    }
}

