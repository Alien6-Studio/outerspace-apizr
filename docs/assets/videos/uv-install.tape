# Source for uv-install.gif (shown in README.md and the install guide).
# Regenerate at each release after bumping the version below:
#   uv tool uninstall outerspace-apizr
#   vhs docs/assets/videos/uv-install.tape
# Requires vhs, ttyd and ffmpeg, plus network access to PyPI.
Output docs/assets/videos/uv-install.gif

Set Shell "bash"
Set FontSize 18
Set Width 1200
Set Height 600
Set Padding 20
Set TypingSpeed 60ms

Type "uv tool install outerspace-apizr==0.4.5"
Enter
Wait+Screen@120s /Installed \d+ executable/
Sleep 1.5s

Type "apizr --version"
Enter
Wait+Screen@30s /0\.4\.5/
Sleep 3s
