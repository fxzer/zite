#!/usr/bin/env sh
set -eu

# Downloads a Zite release from GitHub and unpacks it into ~/.local/.
# Optional: ZITE_VERSION=1.2.3 picks a release, ZITE_BUNDLE_PATH installs a local tarball.
# The ZED_ names of these variables still work for older instructions.

main() {
    platform="$(uname -s)"
    arch="$(uname -m)"
    channel="${ZITE_CHANNEL:-${ZED_CHANNEL:-stable}}"
    repo="fxzer/zite"
    version="${ZITE_VERSION:-${ZED_VERSION:-latest}}"
    bundle_path="${ZITE_BUNDLE_PATH:-${ZED_BUNDLE_PATH:-}}"
    if [ "$version" = "latest" ]; then
        download_base="https://github.com/$repo/releases/latest/download"
    else
        download_base="https://github.com/$repo/releases/download/v$version"
    fi
    # Use TMPDIR if available (for environments with non-standard temp directories)
    if [ -n "${TMPDIR:-}" ] && [ -d "${TMPDIR}" ]; then
        temp="$(mktemp -d "$TMPDIR/zite-XXXXXX")"
    else
        temp="$(mktemp -d "/tmp/zite-XXXXXX")"
    fi

    if [ "$platform" = "Darwin" ]; then
        platform="macos"
    elif [ "$platform" = "Linux" ]; then
        platform="linux"
    else
        echo "Unsupported platform $platform"
        exit 1
    fi

    case "$platform-$arch" in
        macos-arm64* | linux-arm64* | linux-aarch64)
            arch="aarch64"
            ;;
        macos-x86* | linux-x86*)
            arch="x86_64"
            ;;
        *)
            echo "Unsupported platform or architecture"
            exit 1
            ;;
    esac

    if command -v curl >/dev/null 2>&1; then
        curl () {
            command curl -fL "$@"
        }
    elif command -v wget >/dev/null 2>&1; then
        curl () {
            wget -O- "$@"
        }
    else
        echo "Could not find 'curl' or 'wget' in your path"
        exit 1
    fi

    "$platform" "$@"

    if [ "$(command -v zite)" = "$HOME/.local/bin/zite" ]; then
        echo "Zite has been installed. Run with 'zite'"
    else
        echo "To run Zite from your terminal, you must add ~/.local/bin to your PATH"
        echo "Run:"

        case "$SHELL" in
            *zsh)
                echo "   echo 'export PATH=\$HOME/.local/bin:\$PATH' >> ~/.zshrc"
                echo "   source ~/.zshrc"
                ;;
            *fish)
                echo "   fish_add_path -U $HOME/.local/bin"
                ;;
            *)
                echo "   echo 'export PATH=\$HOME/.local/bin:\$PATH' >> ~/.bashrc"
                echo "   source ~/.bashrc"
                ;;
        esac

        echo "To run Zite now, '~/.local/bin/zite'"
    fi
}

linux() {
    if [ -n "$bundle_path" ]; then
        cp "$bundle_path" "$temp/zite-linux-$arch.tar.gz"
    else
        echo "Downloading Zite version: $version"
        curl "$download_base/zite-linux-$arch.tar.gz" > "$temp/zite-linux-$arch.tar.gz"
    fi

    suffix=""
    if [ "$channel" != "stable" ]; then
        suffix="-$channel"
    fi

    appid=""
    case "$channel" in
      stable)
        appid="dev.zed.Zite"
        ;;
      dev)
        appid="dev.zed.Zite-Dev"
        ;;
      *)
        echo "Unknown release channel: ${channel}. Using stable app ID."
        appid="dev.zed.Zite"
        ;;
    esac

    # Unpack
    rm -rf "$HOME/.local/zite$suffix.app"
    mkdir -p "$HOME/.local/zite$suffix.app"
    tar -xzf "$temp/zite-linux-$arch.tar.gz" -C "$HOME/.local/"

    zite_editor="$HOME/.local/zite$suffix.app/libexec/zite-editor"
    if [ -f "$zite_editor" ] && command -v ldd >/dev/null 2>&1; then
        missing="$(ldd "$zite_editor" 2>/dev/null | sed -n 's/^[[:space:]]*\(.*\) => not found$/\1/p')"
        if [ -n "$missing" ]; then
            echo "Warning: your system is missing libraries that Zite needs:"
            echo "$missing" | sed 's/^/    /'
            echo "Install them with your package manager, or Zite will fail to start."
        fi
    fi

    # Setup ~/.local directories
    mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"

    # Link the binary
    ln -sf "$HOME/.local/zite$suffix.app/bin/zite" "$HOME/.local/bin/zite"

    # Copy .desktop file
    desktop_file_path="$HOME/.local/share/applications/${appid}.desktop"
    src_dir="$HOME/.local/zite$suffix.app/share/applications"
    cp "$src_dir/${appid}.desktop" "${desktop_file_path}"
    sed -i "s|Icon=zite|Icon=$HOME/.local/zite$suffix.app/share/icons/hicolor/512x512/apps/zite.png|g" "${desktop_file_path}"
    sed -i "s|Exec=zite|Exec=$HOME/.local/zite$suffix.app/bin/zite|g" "${desktop_file_path}"
}

macos() {
    echo "Downloading Zite version: $version"
    curl "$download_base/Zite-$arch.dmg" > "$temp/Zite-$arch.dmg"
    hdiutil attach -quiet "$temp/Zite-$arch.dmg" -mountpoint "$temp/mount"
    app="$(cd "$temp/mount/"; echo *.app)"
    echo "Installing $app"
    if [ -d "/Applications/$app" ]; then
        echo "Removing existing $app"
        rm -rf "/Applications/$app"
    fi
    ditto "$temp/mount/$app" "/Applications/$app"
    hdiutil detach -quiet "$temp/mount"

    mkdir -p "$HOME/.local/bin"
    # Link the binary
    ln -sf "/Applications/$app/Contents/MacOS/cli" "$HOME/.local/bin/zite"
}

main "$@"
