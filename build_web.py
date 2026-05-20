import pathlib
import subprocess
import sys
import tarfile


ROOT = pathlib.Path(__file__).resolve().parent
GAME_DIR = ROOT / "game"
WEB_DIR = GAME_DIR / "build" / "web"


def main() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pygbag",
            "--ume_block=0",
            "--build",
            str(GAME_DIR),
        ],
        check=True,
    )

    bundle = WEB_DIR / "game.tar.gz"
    source = GAME_DIR / "main.py"
    with tarfile.open(bundle, "w:gz") as tar:
        tar.add(source, arcname="assets/main.py")

    print(f"Created {bundle}")


if __name__ == "__main__":
    main()
