import pathlib
import shutil
import subprocess
import sys
import tarfile


ROOT = pathlib.Path(__file__).resolve().parent
GAME_DIR = ROOT / "game"
WEB_DIR = GAME_DIR / "build" / "web"


def main() -> None:
    build_dir = GAME_DIR / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pygbag",
            "--build",
            "--ume_block",
            "0",
            "--width",
            "1280",
            "--height",
            "720",
            "--title",
            "4x4 Stage 1",
            str(GAME_DIR),
        ],
        check=True,
    )

    # pygbag 0.9.1 serves game.apk. The tar bundle is kept as a harmless
    # compatibility artifact for templates that request it.
    bundle = WEB_DIR / "game.tar.gz"
    source = GAME_DIR / "main.py"
    with tarfile.open(bundle, "w:gz") as tar:
        tar.add(source, arcname="assets/main.py")

    print(f"Created compatibility bundle {bundle}")


if __name__ == "__main__":
    main()
