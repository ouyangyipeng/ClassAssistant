mod backend;

use backend::{Backend, Connection, Launch};
use std::{
    io::Write,
    path::Path,
    sync::{Arc, Mutex},
};
use tauri::{Manager, PhysicalPosition, PhysicalSize, State};
use tauri_plugin_dialog::DialogExt;

#[derive(Default)]
struct WindowMode(Mutex<Option<(PhysicalSize<u32>, PhysicalPosition<i32>)>>);

fn launch_paths(app: &tauri::AppHandle) -> Result<Launch, String> {
    let folder = if cfg!(debug_assertions) {
        "ClassFox Development"
    } else {
        "ClassFox"
    };
    let data = app
        .path()
        .resolve(folder, tauri::path::BaseDirectory::LocalData)
        .map_err(|_| "无法定位用户数据目录")?;
    #[cfg(debug_assertions)]
    let data = std::env::var_os("CLASSFOX_DESKTOP_DATA_DIR")
        .map(std::path::PathBuf::from)
        .unwrap_or(data);
    let directory = app
        .path()
        .resource_dir()
        .map_err(|_| "无法定位应用资源")?
        .join("backend");
    let executable = directory.join(if cfg!(windows) {
        "classfox-service.exe"
    } else {
        "classfox-service"
    });
    #[cfg(debug_assertions)]
    if !executable.is_file() {
        return Ok(backend::development_launch(data));
    }
    Ok(Launch {
        executable,
        directory,
        data,
        arguments: vec![],
    })
}

#[tauri::command]
async fn backend_connection(
    app: tauri::AppHandle,
    backend: State<'_, Arc<Backend>>,
) -> Result<Connection, String> {
    let launch = launch_paths(&app)?;
    let backend = backend.inner().clone();
    tauri::async_runtime::spawn_blocking(move || backend.connection(launch))
        .await
        .map_err(|_| "本地服务启动任务未完成")?
}

#[tauri::command]
fn set_window_mode(
    window: tauri::WebviewWindow,
    state: State<'_, WindowMode>,
    compact: bool,
) -> Result<(), String> {
    let mut saved = state.0.lock().map_err(|_| "无法读取窗口状态")?;
    let result = if compact {
        if saved.is_none() {
            *saved = Some((
                window.inner_size().map_err(|_| "无法读取窗口大小")?,
                window.outer_position().map_err(|_| "无法读取窗口位置")?,
            ));
        }
        window
            .unmaximize()
            .and_then(|()| window.set_min_size(Some(tauri::LogicalSize::new(360.0, 145.0))))
            .and_then(|()| window.set_size(tauri::LogicalSize::new(430.0, 150.0)))
    } else {
        window
            .set_min_size(Some(tauri::LogicalSize::new(860.0, 620.0)))
            .and_then(|()| {
                if let Some((size, position)) = saved.take() {
                    window
                        .set_size(size)
                        .and_then(|()| window.set_position(position))
                } else {
                    window.set_size(tauri::LogicalSize::new(1180.0, 780.0))
                }
            })
    };
    result.map_err(|_| "无法调整窗口大小，请恢复窗口后重试".into())
}

#[tauri::command]
async fn export_text(
    app: tauri::AppHandle,
    content: String,
    filename: String,
) -> Result<bool, String> {
    if content.len() > 32 * 1024 * 1024 {
        return Err("导出内容超过 32 MB，请缩小范围".into());
    }
    let name = Path::new(&filename)
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| !name.is_empty() && name.len() <= 240)
        .ok_or("导出文件名无效")?
        .to_string();
    tauri::async_runtime::spawn_blocking(move || {
        let selected = app
            .dialog()
            .file()
            .set_title("导出课堂记录")
            .set_file_name(name)
            .blocking_save_file();
        let Some(selected) = selected else {
            return Ok(false);
        };
        let path = selected.into_path().map_err(|_| "请选择本机文件路径")?;
        let directory = path.parent().ok_or("请选择有效的保存目录")?;
        let mut temporary =
            tempfile::NamedTempFile::new_in(directory).map_err(|_| "无法在所选目录创建文件")?;
        temporary
            .write_all(content.as_bytes())
            .and_then(|()| temporary.as_file().sync_all())
            .map_err(|_| "写入失败，请检查磁盘空间和目录权限")?;
        temporary
            .persist(path)
            .map_err(|_| "保存失败，原文件已保留，请选择其他位置")?;
        Ok(true)
    })
    .await
    .map_err(|_| "导出任务未完成")?
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(Arc::new(Backend::default()))
        .manage(WindowMode::default())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            backend_connection,
            set_window_mode,
            export_text
        ])
        .build(tauri::generate_context!())
        .expect("Unable to initialize ClassFox")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                app.state::<Arc<Backend>>().shutdown();
            }
        });
}
