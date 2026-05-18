# Whisper-Free Homebrew Cask formula.
#
# Local install (for testing before submitting upstream):
#   brew install --cask ./packaging/homebrew/whisper-free.rb
#
# Submission to homebrew/homebrew-cask (after a stable release):
#   1. Fork homebrew/homebrew-cask
#   2. Copy this file to Casks/w/whisper-free.rb
#   3. brew audit --cask whisper-free --new
#   4. brew style ./Casks/w/whisper-free.rb
#   5. Open PR
#
# Per-release update:
#   brew bump-cask-pr whisper-free \
#     --version 1.0.1 \
#     --sha256 NEW_SHA256_OF_DMG
cask "whisper-free" do
  version "1.0.0"
  sha256 "f836b2957ee7a3892f0d8fcb02bd0460b5a359c88d943711382049cb9549c883"

  url "https://github.com/pradeep512/Whisper-free/releases/download/v#{version}/Whisper-Free-#{version}.dmg",
      verified: "github.com/pradeep512/Whisper-free/"
  name "Whisper-Free"
  desc "Local, privacy-first speech-to-text with Dynamic-Island overlay"
  homepage "https://github.com/pradeep512/Whisper-free"

  # Apple Silicon only — MLX requires Apple Silicon and the build is arm64-only.
  depends_on macos: ">= :ventura"
  depends_on arch: :arm64

  app "Whisper-Free.app"

  # Install the CLI shim. The script is bundled inside the .app at
  # Contents/Resources/whisper-free by the PyInstaller spec; Homebrew Cask's
  # `binary` stanza creates a symlink in /opt/homebrew/bin.
  binary "#{appdir}/Whisper-Free.app/Contents/Resources/whisper-free"

  # PyInstaller drops the executable bit when copying scripts via datas;
  # restore it so the binary symlink is invocable.
  postflight do
    cli_path = "#{appdir}/Whisper-Free.app/Contents/Resources/whisper-free"
    File.chmod(0755, cli_path) if File.exist?(cli_path)
  end

  # Clean up user-state directories on `brew uninstall --cask --zap`.
  zap trash: [
    "~/Library/Application Support/Whisper-Free",
    "~/Library/Caches/Whisper-Free",
    "~/Library/Logs/Whisper-Free",
    "~/Library/Preferences/com.whisperfree.app.plist",
    "~/Library/Saved Application State/com.whisperfree.app.savedState",
  ]

  caveats <<~EOS
    Whisper-Free is currently unsigned. On first launch:

      1. macOS may block the app with "cannot be opened because Apple
         cannot check it for malicious software."

      2. On macOS 13–14: right-click Whisper-Free.app → Open → Open.
         On macOS 15+: System Settings → Privacy & Security → scroll down
         → click "Open Anyway" next to "Whisper-Free was blocked".

      3. Grant Microphone + Accessibility permissions when prompted
         (the onboarding wizard will guide you through this).

    Whisper-Free requires Apple Silicon (M1+). Intel Macs are not supported.
  EOS
end
