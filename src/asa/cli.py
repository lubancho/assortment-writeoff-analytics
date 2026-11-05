"""Командная строка: asa <команда>.

asa check-db                 проверить подключение к PostgreSQL
asa migrate                  применить миграции
asa generate --out data/     записать демо-данные в CSV (для просмотра)
asa load [--reset]           сгенерировать и загрузить демо-данные в БД
asa init-demo                migrate + load, если данных ещё нет (используется в Docker)
asa sql <номер> [--from --to] выполнить SQL-задачу 1–10 и вывести результат
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

from asa.config import DEMO_SEED, get_settings
from asa.logging_setup import setup_logging

log = logging.getLogger("asa.cli")


def _wait_for_db(attempts: int = 30) -> str:
    from asa.db import check_connection

    for i in range(1, attempts + 1):
        try:
            return check_connection()
        except Exception as exc:
            log.warning("БД недоступна (попытка %s/%s): %s", i, attempts, exc)
            time.sleep(2)
    raise SystemExit("Не удалось подключиться к PostgreSQL")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="asa", description="Анализ продаж, ассортимента и списаний"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-db")
    sub.add_parser("migrate")
    g = sub.add_parser("generate")
    g.add_argument("--out", type=Path, default=Path("data"))
    g.add_argument("--seed", type=int, default=DEMO_SEED)
    ld = sub.add_parser("load")
    ld.add_argument("--reset", action="store_true", help="очистить данные перед загрузкой")
    ld.add_argument("--seed", type=int, default=DEMO_SEED)
    sub.add_parser("init-demo")
    sq = sub.add_parser("sql")
    sq.add_argument("number", type=int, choices=range(1, 11))
    sq.add_argument("--from", dest="d0", type=date.fromisoformat, default=None)
    sq.add_argument("--to", dest="d1", type=date.fromisoformat, default=None)
    args = parser.parse_args(argv)

    try:
        setup_logging(get_settings().log_level)
    except RuntimeError:
        setup_logging("INFO")

    if args.cmd == "generate":
        from asa.generator import build_demo, save_csv

        files = save_csv(build_demo(args.seed), args.out)
        log.info("Записано файлов: %s в %s", len(files), args.out)
        return 0

    from asa.db import connect

    if args.cmd == "check-db":
        log.info("Подключение есть: %s", _wait_for_db())
        return 0
    if args.cmd == "migrate":
        from asa.migrate import migrate

        _wait_for_db()
        with connect() as conn:
            migrate(conn)
        return 0
    if args.cmd in ("load", "init-demo"):
        from asa.generator import build_demo
        from asa.loader import is_loaded, load_demo, reset
        from asa.migrate import migrate

        _wait_for_db()
        with connect() as conn:
            if args.cmd == "init-demo":
                migrate(conn)
            if is_loaded(conn):
                if args.cmd == "init-demo" or not args.reset:
                    log.info(
                        "Данные уже загружены — пропускаю (для перезагрузки: asa load --reset)"
                    )
                    return 0
                reset(conn)
            load_demo(conn, build_demo(getattr(args, "seed", DEMO_SEED)))
        return 0
    if args.cmd == "sql":
        import pandas as pd

        from asa import queries, repository

        with connect() as conn:
            d0, d1 = repository.data_period(conn)
            d0, d1 = args.d0 or d0, args.d1 or d1
            df = queries.run(conn, args.number, d0, d1)
        with pd.option_context("display.max_rows", 40, "display.width", 200):
            print(f"SQL-задача {args.number}: {queries.TASKS[args.number].title} ({d0} — {d1})")
            print(df)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
