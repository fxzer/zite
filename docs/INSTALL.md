## Install

All releases are available [here](https://github.com/fxzer/zite/releases/latest).

### macOS (Apple Silicon and Intel)

1. Download the installer for your Mac, open it, and drag Zite into your Applications folder.
    - [**Apple Silicon**](https://github.com/fxzer/zite/releases/latest/download/Zite-aarch64.dmg) (M1 and later)
    - [**Intel**](https://github.com/fxzer/zite/releases/latest/download/Zite-x86_64.dmg)

   Zite is not signed with an Apple Developer certificate yet, so macOS will block it the first time you open it.
2. Open Terminal and run:

   ```sh
   xattr -d com.apple.quarantine /Applications/Zite.app
   ```

> If you'd rather not use Terminal: open Zite once (you'll see a "Zite can't be opened" or "Apple could not verify" message), then go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to Zite. Confirm with your password.

3. Open Zite normally.

#### Command line

To open files and folders from Terminal with `zite`, choose **Zite → Install CLI** from the menu bar. It adds `zite` to `/usr/local/bin` and may ask for your password.

If that fails, for example because your account isn't an admin, add it yourself without a password:

```sh
mkdir -p ~/.local/bin
ln -sf /Applications/Zite.app/Contents/MacOS/cli ~/.local/bin/zite
```

If `zite` still isn't found, add `~/.local/bin` to your `PATH` by adding this line to `~/.zshrc`, then open a new Terminal window:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

### Linux (x86-64 and AArch64)

Run this in a terminal:

```sh
curl -fsSL https://github.com/fxzer/zite/install.sh | sh
```

It installs Zite into `~/.local`, adds the `zite` command, and adds Zite to your app menu with its icon. Run it again any time to reinstall. Zite keeps itself up to date after that.

#### Manual install

1. Download the tarball for your platform.
    - [**Linux x86-64**](https://github.com/fxzer/zite/releases/latest/download/zite-linux-x86_64.tar.gz)
    - [**Linux AArch64**](https://github.com/fxzer/zite/releases/latest/download/zite-linux-aarch64.tar.gz)

2. Unpack its contents into `~/.local`:

```sh
tar -xzf zite-linux-$(uname -m).tar.gz -C ~/.local
ln -sf ~/.local/zite.app/bin/zite ~/.local/bin/zite
```

Make sure `~/.local/bin` is on your `PATH`, then run `zite`. This doesn't add Zite to your app menu; the install command above does.

#### WSL2

On WSL2, Zite draws with the CPU by default because the WSL GPU driver isn't fully standards-compliant. To try the GPU instead, start Zite with:

```sh
WGPU_ALLOW_UNDERLYING_NONCOMPLIANT_ADAPTER=1 zite
```

### Windows (x86-64)

Download the [installer](https://github.com/fxzer/zite/releases/latest/download/Zite-x86_64.exe) and click to run. The installer isn't code-signed, so Windows SmartScreen may warn you. Click **More info**, then **Run anyway**.
