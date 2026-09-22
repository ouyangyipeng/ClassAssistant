use serde::{Deserialize, Serialize};
use std::{
    io::{BufRead, BufReader, Read, Write},
    net::{SocketAddr, TcpStream},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Mutex,
    },
    time::{Duration, Instant},
};

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Connection {
    pub base_url: String,
    pub token: String,
}

#[derive(Deserialize)]
struct Ready {
    #[serde(rename = "type")]
    kind: String,
    port: u16,
    token: String,
    version: String,
}

pub struct Launch {
    pub executable: PathBuf,
    pub arguments: Vec<String>,
    pub directory: PathBuf,
    pub data: PathBuf,
}

struct OwnedBackend {
    child: Child,
    connection: Connection,
}

impl OwnedBackend {
    fn stop(&mut self) {
        if let Some(mut input) = self.child.stdin.take() {
            let _ = input.write_all(b"{\"action\":\"stop\"}\n");
        }
        let deadline = Instant::now() + Duration::from_secs(25);
        while Instant::now() < deadline {
            if matches!(self.child.try_wait(), Ok(Some(_))) {
                return;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for OwnedBackend {
    fn drop(&mut self) {
        self.stop();
    }
}

#[derive(Default)]
pub struct Backend {
    child: Mutex<Option<OwnedBackend>>,
    exiting: AtomicBool,
}

impl Backend {
    pub fn connection(&self, launch: Launch) -> Result<Connection, String> {
        let mut state = self
            .child
            .lock()
            .map_err(|_| "本地服务状态无法读取，请重启应用")?;
        if self.exiting.load(Ordering::Relaxed) {
            return Err("应用正在退出".into());
        }
        if let Some(backend) = state.as_mut() {
            if matches!(backend.child.try_wait(), Ok(None)) {
                return Ok(backend.connection.clone());
            }
        }
        *state = None;
        let mut owned = spawn(launch)?;
        let connection = handshake(&mut owned.child, &self.exiting)?;
        owned.connection = connection.clone();
        *state = Some(owned);
        Ok(connection)
    }

    pub fn shutdown(&self) {
        self.exiting.store(true, Ordering::Relaxed);
        if let Ok(mut state) = self.child.lock() {
            *state = None;
        }
    }
}

fn spawn(launch: Launch) -> Result<OwnedBackend, String> {
    if !launch.executable.is_file() {
        return Err(
            "缺少本地服务。源码运行请先同步 Python 环境；安装版请重新安装完整应用。".into(),
        );
    }
    let mut command = Command::new(launch.executable);
    command
        .args(launch.arguments)
        .arg("--desktop")
        .current_dir(launch.directory)
        .env_clear()
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    for name in [
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "TMP",
        "TEMP",
        "SYSTEMROOT",
        "WINDIR",
        "APPDATA",
        "LOCALAPPDATA",
    ] {
        if let Some(value) = std::env::var_os(name) {
            command.env(name, value);
        }
    }
    command.env("PYTHONUNBUFFERED", "1");
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let child = command
        .spawn()
        .map_err(|_| "无法启动本地服务，请检查安装完整性与执行权限")?;
    let mut owned = OwnedBackend {
        child,
        connection: Connection {
            base_url: String::new(),
            token: String::new(),
        },
    };
    let request = serde_json::to_vec(&serde_json::json!({"data_dir": launch.data}))
        .map_err(|_| "数据目录无法编码")?;
    let input = owned.child.stdin.as_mut().ok_or("本地服务启动管道不可用")?;
    input
        .write_all(&request)
        .and_then(|()| input.write_all(b"\n"))
        .map_err(|_| "无法初始化本地服务")?;
    Ok(owned)
}

fn handshake(child: &mut Child, exiting: &AtomicBool) -> Result<Connection, String> {
    let output = child.stdout.take().ok_or("本地服务输出管道不可用")?;
    let (sender, receiver) = mpsc::sync_channel(1);
    std::thread::spawn(move || {
        let mut line = String::new();
        let result = BufReader::new(output.take(4096))
            .read_line(&mut line)
            .map(|_| line);
        let _ = sender.send(result);
    });
    let deadline = Instant::now() + Duration::from_secs(45);
    loop {
        if exiting.load(Ordering::Relaxed) {
            return Err("应用正在退出".into());
        }
        if Instant::now() >= deadline {
            return Err("本地服务启动超时，请检查数据目录或重新安装".into());
        }
        match receiver.recv_timeout(Duration::from_millis(100)) {
            Ok(Ok(line)) => return validate_ready(&line),
            Err(mpsc::RecvTimeoutError::Timeout) => continue,
            _ => return Err("本地服务在启动时退出，请检查安装完整性".into()),
        }
    }
}

fn validate_ready(line: &str) -> Result<Connection, String> {
    if let Ok(value) = serde_json::from_str::<serde_json::Value>(line) {
        if value["type"] == "error" && value["code"] == "DataDirectoryInUse" {
            return Err(
                "此数据目录已由另一个课狐窗口使用，请返回原窗口，或关闭原窗口后重新连接".into(),
            );
        }
    }
    let ready: Ready = serde_json::from_str(line)
        .map_err(|_| "本地服务未完成启动，请检查数据目录权限和安装完整性")?;
    if ready.kind != "ready"
        || ready.port == 0
        || ready.version != env!("CARGO_PKG_VERSION")
        || !(32..=128).contains(&ready.token.len())
        || !ready
            .token
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
    {
        return Err("本地服务版本或连接信息不匹配，请重新安装完整应用".into());
    }
    authenticate(ready.port, &ready.token)?;
    Ok(Connection {
        base_url: format!("http://127.0.0.1:{}", ready.port),
        token: ready.token,
    })
}

fn authenticate(port: u16, token: &str) -> Result<(), String> {
    let error = || "本地服务未通过身份检查，请重新启动应用".to_string();
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let mut socket =
        TcpStream::connect_timeout(&address, Duration::from_secs(2)).map_err(|_| error())?;
    socket
        .set_read_timeout(Some(Duration::from_secs(2)))
        .map_err(|_| error())?;
    socket
        .set_write_timeout(Some(Duration::from_secs(2)))
        .map_err(|_| error())?;
    let request = format!("GET /api/v2/status HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: Bearer {token}\r\nConnection: close\r\n\r\n");
    socket.write_all(request.as_bytes()).map_err(|_| error())?;
    let mut status = String::new();
    BufReader::new(socket.take(256))
        .read_line(&mut status)
        .map_err(|_| error())?;
    if !status.starts_with("HTTP/1.1 200 ") {
        return Err(error());
    }
    Ok(())
}

#[cfg(any(debug_assertions, test))]
pub fn development_launch(data: PathBuf) -> Launch {
    let directory = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../api-service");
    let python = if cfg!(windows) {
        ".venv/Scripts/python.exe"
    } else {
        ".venv/bin/python"
    };
    Launch {
        executable: directory.join(python),
        arguments: vec!["-u".into(), "main.py".into()],
        directory,
        data,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_invalid_readiness_without_exposing_values() {
        assert!(
            validate_ready(r#"{"type":"error","code":"DataDirectoryInUse"}"#)
                .err()
                .unwrap()
                .contains("另一个课狐窗口")
        );
        for input in [
            "invalid",
            r#"{"type":"error","message":"synthetic-private-detail"}"#,
            r#"{"type":"ready","port":8765,"token":"bad\r\nheader","version":"2.0.0"}"#,
        ] {
            let result = validate_ready(input);
            assert!(result.is_err());
            assert!(!result.err().unwrap().contains("synthetic-private-detail"));
        }
    }

    #[test]
    fn refuses_a_reachable_service_without_authentication() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = std::thread::spawn(move || {
            let (mut connection, _) = listener.accept().unwrap();
            let mut buffer = [0; 2048];
            assert!(connection.read(&mut buffer).unwrap() > 0);
            connection
                .write_all(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n")
                .unwrap();
        });
        assert!(authenticate(port, "synthetic-private-token").is_err());
        server.join().unwrap();
    }

    #[test]
    fn starts_and_stops_only_its_own_backend() {
        let directory = tempfile::tempdir().unwrap();
        let unrelated = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let backend = Backend::default();
        let connection = backend
            .connection(development_launch(directory.path().join("中文 data")))
            .unwrap();
        let again = backend
            .connection(development_launch(directory.path().join("中文 data")))
            .unwrap();
        assert!(connection.base_url == again.base_url && connection.token == again.token);
        let port: u16 = connection
            .base_url
            .rsplit(':')
            .next()
            .unwrap()
            .parse()
            .unwrap();
        assert!(authenticate(port, &connection.token).is_ok());
        backend.shutdown();
        assert!(TcpStream::connect(("127.0.0.1", port)).is_err());
        assert!(TcpStream::connect(unrelated.local_addr().unwrap()).is_ok());
    }
}
