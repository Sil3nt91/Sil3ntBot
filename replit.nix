{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.ffmpeg
    pkgs.libopus  # Aggiungi la libreria Opus
  ];
}