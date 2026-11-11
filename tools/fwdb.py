#!/usr/bin/env python3
"""Build and query a SQLite index of a Ghidra firmware export.

Input is an export dir from tools/ghidra/ExportFw.java:
    functions.jsonl   one JSON object per function
    refs.csv          from,to,kind
    decomp/*.c        decompiled C (grep separately)

    python fwdb.py build out/ghidra/fwu107 [--db out/fw.sqlite --image fwu107]
    python fwdb.py q    out/fw.sqlite "SELECT ..."        # raw SQL
    python fwdb.py refsto out/fw.sqlite 0x0801bddc        # who references an address

Tables: functions(entry,name,size,strings), refs(src,dst,kind,func).
Addresses are stored as integers. One image per DB (keep images in
separate .sqlite files, like the digikit cfdb workflow).
"""
from __future__ import annotations
import csv, json, sqlite3, sys, os

SCHEMA = """
CREATE TABLE functions(entry INTEGER PRIMARY KEY, name TEXT, size INTEGER, strings TEXT);
CREATE INDEX functions_name ON functions(name);
CREATE TABLE refs(src INTEGER, dst INTEGER, kind TEXT, func INTEGER);
CREATE INDEX refs_dst ON refs(dst);
CREATE INDEX refs_src ON refs(src);
CREATE INDEX refs_func ON refs(func);
"""


def build(export_dir: str, db_path: str) -> None:
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    # functions + a lookup of entry ranges for attributing refs to a function
    funcs = []
    with open(os.path.join(export_dir, "functions.jsonl")) as f:
        for line in f:
            o = json.loads(line)
            entry = int(o["entry"], 16)
            funcs.append((entry, o["name"], o["size"], json.dumps(o.get("strings", []))))
    con.executemany("INSERT INTO functions VALUES(?,?,?,?)", funcs)
    ranges = sorted((e, e + s) for e, _, s, _ in funcs)

    def owner(addr: int) -> int | None:
        lo, hi = 0, len(ranges)
        while lo < hi:
            mid = (lo + hi) // 2
            if ranges[mid][0] <= addr < ranges[mid][1]:
                return ranges[mid][0]
            if ranges[mid][0] > addr:
                hi = mid
            else:
                lo = mid + 1
        return None

    rows = []
    with open(os.path.join(export_dir, "refs.csv")) as f:
        for r in csv.DictReader(f):
            src = int(r["from"], 16)
            dst = int(r["to"], 16)
            if src > 0xFFFFFFFF or dst > 0xFFFFFFFF:  # register/unknown space
                continue
            rows.append((src, dst, r["kind"], owner(src)))
    con.executemany("INSERT INTO refs VALUES(?,?,?,?)", rows)
    con.commit()
    print(f"built {db_path}: {len(funcs)} functions, {len(rows)} refs")
    con.close()


def q(db_path: str, sql: str) -> None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    for row in con.execute(sql):
        print("  ".join(
            (f"{v:#x}" if isinstance(v, int) and abs(v) > 0x1000 else str(v))
            for v in row))
    con.close()


def refsto(db_path: str, addr_hex: str) -> None:
    addr = int(addr_hex, 16)
    q(db_path,
      f"SELECT printf('%x',r.src) src, r.kind, printf('%x',f.entry) func, f.name "
      f"FROM refs r LEFT JOIN functions f ON f.entry=r.func WHERE r.dst={addr}")


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    cmd = argv[1]
    if cmd == "build":
        export = argv[2]
        db = "out/fw.sqlite";
        if "--db" in argv: db = argv[argv.index("--db") + 1]
        build(export, db)
    elif cmd == "q":
        q(argv[2], argv[3])
    elif cmd == "refsto":
        refsto(argv[2], argv[3])
    else:
        print(__doc__); return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
