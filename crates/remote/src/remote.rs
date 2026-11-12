pub mod command;
pub mod json_log;
pub mod protocol;
pub mod proxy;
pub mod remote_client;
pub mod remote_identity;
mod transport;

#[cfg(target_os = "windows")]
pub use remote_client::OpenWslPath;
pub use remote_client::{
    CommandTemplate, ConnectionIdentifier, ConnectionState, Interactive, RemoteArch, RemoteClient,
    RemoteClientDelegate, RemoteClientEvent, RemoteConnection, RemoteConnectionOptions, RemoteOs,
    RemotePlatform, connect, has_active_connection,
};
<<<<<<< e3e073dad02b44f8751c5b4ef6759a2318bb76b2
pub use remote_identity::{
    RemoteConnectionIdentity, remote_connection_identity, same_remote_connection_identity,
};
=======
pub use remote_identity::RemoteConnectionIdentity;
pub use transport::docker::DockerConnectionOptions;
>>>>>>> a35471982d8acd6ebe16871b9e9b626ab8c781ef
pub use transport::ssh::{SshConnectionOptions, SshPortForwardOption};
pub use transport::wsl::WslConnectionOptions;
#[cfg(target_os = "windows")]
pub use transport::wsl::wsl_path_to_windows_path;

#[cfg(any(test, feature = "test-support"))]
pub use transport::mock::{
    MOCK_STDIO_FRAME_HEX, MockConnection, MockConnectionOptions, MockConnectionRegistry,
    MockDelegate,
};
