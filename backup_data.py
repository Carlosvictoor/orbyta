from datetime import datetime
from pathlib import Path
import zipfile

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = BASE_DIR / "backups"


def main():
    BACKUP_DIR.mkdir(exist_ok=True)

    if not DATA_DIR.exists():
        raise SystemExit("Pasta 'data' não encontrada para backup.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = BACKUP_DIR / f"backup_data_{stamp}.zip"

    with zipfile.ZipFile(out_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in DATA_DIR.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(BASE_DIR))

    print(f"Backup criado com sucesso: {out_file}")


if __name__ == "__main__":
    main()
