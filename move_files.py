"""
Скрипт для перемещения файлов в новую структуру проекта.
"""
import os
import shutil
from pathlib import Path


def move_files():
    """Переместить файлы в новую структуру проекта."""
    base_dir = Path(".")
    fast_cache_dir = base_dir / "fast_cache_middleware"
    core_dir = fast_cache_dir / "core"
    examples_dir = fast_cache_dir / "examples"
    new_examples_dir = base_dir / "examples"
    tests_dir = base_dir / "tests"
    docs_dir = base_dir / "docs"

    # Перемещаем файлы из core в fast_cache_middleware
    if core_dir.exists():
        for file in core_dir.glob("*.py"):
            try:
                target = fast_cache_dir / file.name
                if target.exists():
                    print(f"Файл {target} уже существует, пропускаем")
                    continue
                print(f"Перемещаем {file} в {target}")
                shutil.copy2(str(file), str(target))
                os.remove(str(file))
            except Exception as e:
                print(f"Ошибка при перемещении {file}: {e}")
        try:
            os.rmdir(core_dir)
            print(f"Удалена директория {core_dir}")
        except Exception as e:
            print(f"Ошибка при удалении {core_dir}: {e}")

    # Перемещаем примеры
    if examples_dir.exists():
        for file in examples_dir.glob("*.py"):
            try:
                target = new_examples_dir / file.name
                if target.exists():
                    print(f"Файл {target} уже существует, пропускаем")
                    continue
                print(f"Перемещаем {file} в {target}")
                shutil.copy2(str(file), str(target))
                os.remove(str(file))
            except Exception as e:
                print(f"Ошибка при перемещении {file}: {e}")
        try:
            os.rmdir(examples_dir)
            print(f"Удалена директория {examples_dir}")
        except Exception as e:
            print(f"Ошибка при удалении {examples_dir}: {e}")

    # Создаем __init__.py в новых директориях
    for dir_path in [new_examples_dir, tests_dir, docs_dir]:
        init_file = dir_path / "__init__.py"
        if not init_file.exists():
            try:
                init_file.touch()
                print(f"Создан файл {init_file}")
            except Exception as e:
                print(f"Ошибка при создании {init_file}: {e}")


if __name__ == "__main__":
    move_files() 