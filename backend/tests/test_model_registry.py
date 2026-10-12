import subprocess
import sys

from app.config import BACKEND_DIR

CHECK = (
    "from app import create_app\n"
    "from app.config import Settings\n"
    "from app.database import Base\n"
    "create_app(Settings(_env_file=None))\n"
    "print(len(Base.metadata.sorted_tables))\n"
)


def test_app_registers_every_model_without_alembic():
    result = subprocess.run(
        [sys.executable, "-c", CHECK],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert int(result.stdout) == 10
