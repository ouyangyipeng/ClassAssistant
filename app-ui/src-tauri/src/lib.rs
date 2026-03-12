use std::{
    fs::OpenOptions,
    io::Write,
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{LazyLock, Mutex},
    time::{Duration, Instant},
    fs,
};

use serde::Serialize;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

static BACKEND_CHILD: LazyLock<Mutex<Option<Child>>> = LazyLock::new(|| Mutex::new(None));

#[derive(Serialize)]
struct BackendBootstrapResult {
    status: String,
    message: String,
}

// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

fn build_bootstrap_result(status: &str, message: impl Into<String>) -> BackendBootstrapResult {
    BackendBootstrapResult {
        status: status.to_string(),
        message: message.into(),
    }
}

#[cfg(not(debug_assertions))]
fn append_startup_log(app_root: &Path, message: &str) {
    let data_dir = startup_log_root(app_root).join("data");
    let _ = std::fs::create_dir_all(&data_dir);
    let log_path = data_dir.join("_startup_rust.log");

    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(log_path) {
        let _ = writeln!(file, "{message}");
    }
}

#[cfg(all(not(debug_assertions), target_os = "macos"))]
fn startup_log_root(_app_root: &Path) -> PathBuf {
    mac_support_root().unwrap_or_else(|_| std::env::temp_dir().join("ClassFox"))
}

#[cfg(all(not(debug_assertions), not(target_os = "macos")))]
fn startup_log_root(app_root: &Path) -> PathBuf {
    app_root.to_path_buf()
}

#[cfg(not(debug_assertions))]
fn current_app_root() -> Result<PathBuf, String> {
    std::env::current_exe()
        .map_err(|err| format!("无法定位当前程序路径: {err}"))?
        .parent()
        .map(Path::to_path_buf)
        .ok_or_else(|| "无法解析程序所在目录".to_string())
}

#[cfg(not(debug_assertions))]
fn ensure_backend_env(backend_dir: &Path) -> Result<bool, String> {
    let env_path = backend_dir.join(".env");
    if env_path.exists() {
        return Ok(false);
    }

    let example_path = backend_dir.join(".env.example");
    if !example_path.exists() {
        return Err("缺少 backend/.env.example，无法初始化配置".to_string());
    }

    fs::copy(&example_path, &env_path).map_err(|err| format!("初始化 .env 失败: {err}"))?;
    Ok(true)
}

#[cfg(not(debug_assertions))]
fn read_backend_port(backend_dir: &Path) -> u16 {
    let env_path = backend_dir.join(".env");
    let content = fs::read_to_string(env_path).unwrap_or_default();

    content
        .lines()
        .find_map(|line| {
            let trimmed = line.trim();
            if trimmed.starts_with("API_PORT=") {
                trimmed
                    .split_once('=')
                    .and_then(|(_, value)| value.trim().parse::<u16>().ok())
            } else {
                None
            }
        })
        .unwrap_or(8765)
}

#[cfg(not(debug_assertions))]
fn wait_for_backend_port(port: u16, timeout: Duration) -> Result<(), String> {
    let deadline = Instant::now() + timeout;

    while Instant::now() < deadline {
        let address = SocketAddr::from(([127, 0, 0, 1], port));
        if TcpStream::connect_timeout(&address, Duration::from_millis(350)).is_ok() {
            return Ok(());
        }

        std::thread::sleep(Duration::from_millis(300));
    }

    Err(format!("后端端口 {port} 在规定时间内未就绪"))
}

#[cfg(all(not(debug_assertions), target_os = "windows"))]
fn spawn_hidden_backend(backend_dir: &Path, runtime_dir: &Path) -> Result<Child, String> {
    let backend_exe = backend_dir.join("class-assistant-backend.exe");
    if !backend_exe.exists() {
        return Err("未找到 backend/class-assistant-backend.exe".to_string());
    }

    let mut command = Command::new(backend_exe);
    command
        .current_dir(runtime_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .creation_flags(CREATE_NO_WINDOW);

    command
        .spawn()
        .map_err(|err| format!("启动后端失败: {err}"))
}

#[cfg(all(not(debug_assertions), target_os = "macos"))]
fn mac_support_root() -> Result<PathBuf, String> {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .map(|home| home.join("Library").join("Application Support").join("ClassFox"))
        .ok_or_else(|| "无法定位 HOME 目录".to_string())
}

#[cfg(all(not(debug_assertions), target_os = "macos"))]
fn prepare_mac_runtime_backend(bundle_backend_dir: &Path) -> Result<(PathBuf, bool), String> {
    let runtime_root = mac_support_root()?;
    let runtime_backend_dir = runtime_root.join("backend");
    fs::create_dir_all(&runtime_backend_dir)
        .map_err(|err| format!("初始化 macOS 运行目录失败: {err}"))?;

    let example_src = bundle_backend_dir.join(".env.example");
    let example_dst = runtime_backend_dir.join(".env.example");
    if example_src.exists() && !example_dst.exists() {
        fs::copy(&example_src, &example_dst)
            .map_err(|err| format!("复制 .env.example 到运行目录失败: {err}"))?;
    }

    let env_dst = runtime_backend_dir.join(".env");
    let env_created = if env_dst.exists() {
        false
    } else if example_src.exists() {
        fs::copy(&example_src, &env_dst)
            .map_err(|err| format!("初始化 .env 到运行目录失败: {err}"))?;
        true
    } else {
        return Err("缺少 backend/.env.example，无法初始化 macOS 运行配置".to_string());
    };

    Ok((runtime_backend_dir, env_created))
}

#[cfg(all(not(debug_assertions), target_os = "macos"))]
fn spawn_hidden_backend(backend_dir: &Path, runtime_dir: &Path) -> Result<Child, String> {
    append_startup_log(backend_dir, &format!("spawn_hidden_backend called with dir: {:?}", backend_dir));

    // For macOS, we prioritize the Resources/backend folder in the app bundle
    let mut final_exe = backend_dir.join("class-assistant-backend");

    if !final_exe.exists() {
        // Try to find Resources/backend
        // backend_dir is Contents/MacOS/backend
        // Contents/MacOS/backend -> Contents/MacOS/ -> Contents/ -> Contents/Resources/backend
        if let Some(contents_dir) = backend_dir.parent().and_then(|p| p.parent()) {
            let resources_backend = contents_dir.join("Resources").join("backend");
            let resources_exe = resources_backend.join("class-assistant-backend");

            append_startup_log(backend_dir, &format!("Trying Resources path: {:?}", resources_exe));

            if resources_exe.exists() {
                append_startup_log(backend_dir, "Backend found in Resources/backend");
                final_exe = resources_exe;
            }
        }
    }

    if !final_exe.exists() {
        return Err(format!("未找到 backend/class-assistant-backend，搜索路径: {:?}", final_exe));
    }

    append_startup_log(backend_dir, &format!("Final backend exe: {:?}", final_exe));
    append_startup_log(backend_dir, &format!("Working dir: {:?}", runtime_dir));

    // Make sure the backend executable has execute permission
    use std::os::unix::fs::PermissionsExt;
    if let Ok(metadata) = fs::metadata(&final_exe) {
        let mut perms = metadata.permissions();
        perms.set_mode(0o755);
        let _ = fs::set_permissions(&final_exe, perms);
    }

    let mut command = Command::new(&final_exe);
    command
        .current_dir(runtime_dir)
        .env("CLASSFOX_PROJECT_ROOT", mac_support_root()?)
        .env("CLASSFOX_ENV_PATH", runtime_dir.join(".env"))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    command
        .spawn()
        .map_err(|err| format!("启动后端失败: {err}"))
}

#[cfg(all(not(debug_assertions), target_os = "windows"))]
fn run_hidden_command(program: &str, args: &[&str]) {
    let mut command = Command::new(program);
    command
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .creation_flags(CREATE_NO_WINDOW);

    let _ = command.status();
}

#[cfg(all(not(debug_assertions), target_os = "windows"))]
fn run_hidden_powershell(script: &str) {
    run_hidden_command("powershell", &["-NoProfile", "-Command", script]);
}

#[cfg(all(not(debug_assertions), target_os = "macos"))]
fn run_hidden_command(program: &str, args: &[&str]) {
    let mut command = Command::new(program);
    command
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    let _ = command.status();
}

#[cfg(all(not(debug_assertions), any(target_os = "windows", target_os = "macos")))]
fn start_embedded_backend() -> Result<BackendBootstrapResult, String> {
    cleanup_backend_processes(false);

    let app_root = current_app_root()?;
    append_startup_log(&app_root, "start_embedded_backend invoked");

    // macOS path resolution: try MacOS/backend first, then Resources/backend
    let mut backend_dir = app_root.join("backend");

    #[cfg(target_os = "macos")]
    if !backend_dir.exists() {
        // app_root is Contents/MacOS/
        if let Some(contents_dir) = app_root.parent() {
            let resources_backend = contents_dir.join("Resources").join("backend");
            if resources_backend.exists() {
                backend_dir = resources_backend;
            }
        }
    }

    if !backend_dir.exists() {
        append_startup_log(&app_root, &format!("backend directory missing at {:?}", backend_dir));
        return Ok(build_bootstrap_result(
            "error",
            "发布目录缺少 backend 文件夹，请重新解压完整安装包。",
        ));
    }

    #[cfg(target_os = "macos")]
    let (runtime_backend_dir, env_created) = prepare_mac_runtime_backend(&backend_dir)?;

    #[cfg(target_os = "windows")]
    let (runtime_backend_dir, env_created) = {
        let env_created = ensure_backend_env(&backend_dir)?;
        (backend_dir.clone(), env_created)
    };

    if env_created {
        append_startup_log(&app_root, "backend .env created from template");
    }

    let port = read_backend_port(&runtime_backend_dir);
    append_startup_log(
        &app_root,
        &format!(
            "starting backend on port {port} from bundle {:?}, runtime {:?}",
            backend_dir, runtime_backend_dir
        ),
    );
    let child = spawn_hidden_backend(&backend_dir, &runtime_backend_dir)?;
    let mut guard = BACKEND_CHILD.lock().expect("backend child mutex poisoned");
    *guard = Some(child);

    match wait_for_backend_port(port, Duration::from_secs(15)) {
        Ok(()) => {
            append_startup_log(&app_root, "backend port became reachable");
            Ok(build_bootstrap_result(
                "ready",
                if env_created {
                    "首次启动已自动生成 backend/.env，当前已直接进入主界面；如需填写 API Key，可稍后在设置中补充。"
                } else {
                    "本地服务启动中，正在连接课堂守候链路。"
                },
            ))
        }
        Err(err) => {
            append_startup_log(&app_root, &format!("backend readiness failed: {err}"));
            Err(format!("后端已启动但未就绪：{err}"))
        }
    }
}

#[cfg(any(debug_assertions, not(any(target_os = "windows", target_os = "macos"))))]
fn start_embedded_backend() -> Result<BackendBootstrapResult, String> {
    Ok(build_bootstrap_result(
        "ready",
        "开发模式不拦截主窗口启动。",
    ))
}

fn finish_startup(app_handle: &tauri::AppHandle) {
    if let Some(splash_window) = app_handle.get_webview_window("splash") {
        let _ = splash_window.close();
    }

    if let Some(main_window) = app_handle.get_webview_window("main") {
        let _ = main_window.show();
        let _ = main_window.set_focus();
    }
}

#[cfg(all(not(debug_assertions), target_os = "windows"))]
fn cleanup_backend_processes(graceful_stop: bool) {
    if let Ok(mut guard) = BACKEND_CHILD.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    if graceful_stop {
        run_hidden_powershell("try { Invoke-WebRequest -Uri 'http://127.0.0.1:8765/api/stop_monitor' -Method Post -UseBasicParsing -TimeoutSec 2 | Out-Null } catch {}");
    }

    run_hidden_command("taskkill", &["/IM", "class-assistant-backend.exe", "/F"]);
    run_hidden_command("taskkill", &["/FI", "WINDOWTITLE eq ClassAssistant-Backend", "/F"]);
    run_hidden_powershell("$portPids = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($portPid in $portPids) { Stop-Process -Id $portPid -Force -ErrorAction SilentlyContinue }");
}

#[cfg(all(not(debug_assertions), target_os = "macos"))]
fn cleanup_backend_processes(graceful_stop: bool) {
    if let Ok(mut guard) = BACKEND_CHILD.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    if graceful_stop {
        // Gracefully stop backend via API
        run_hidden_command("curl", &["-s", "-X", "POST", "http://127.0.0.1:8765/api/stop_monitor"]);
    }

    // Kill backend process by name
    run_hidden_command("pkill", &["-f", "class-assistant-backend"]);

    // Kill any process listening on port 8765 using shell
    let _ = Command::new("sh")
        .args(&["-c", "lsof -ti:8765 -s TCP:LISTEN | xargs kill -9 2>/dev/null"])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

#[cfg(any(debug_assertions, not(any(target_os = "windows", target_os = "macos"))))]
fn cleanup_backend_processes(_graceful_stop: bool) {}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![greet])
        .setup(|app| {
            let app_handle = app.handle().clone();

            #[cfg(debug_assertions)]
            {
                finish_startup(&app_handle);
            }

            #[cfg(all(not(debug_assertions), any(target_os = "windows", target_os = "macos")))]
            {
                if let Some(main_window) = app_handle.get_webview_window("main") {
                    let _ = main_window.hide();
                }

                let _ = WebviewWindowBuilder::new(
                    app,
                    "splash",
                    WebviewUrl::App("index.html".into()),
                )
                .title("ClassFox Splash")
                .inner_size(240.0, 220.0)
                .resizable(false)
                .decorations(false)
                .always_on_top(true)
                .skip_taskbar(true)
                .center()
                .build()?;

                std::thread::spawn(move || {
                    let startup_result = start_embedded_backend();

                    #[cfg(not(debug_assertions))]
                    if let Ok(app_root) = current_app_root() {
                        match &startup_result {
                            Ok(result) => append_startup_log(&app_root, &format!("startup result: {}", result.message)),
                            Err(error) => append_startup_log(&app_root, &format!("startup error: {error}")),
                        }
                    }

                    finish_startup(&app_handle);
                });
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                cleanup_backend_processes(true);
            }
        });
}
