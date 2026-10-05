"""Neutralize spreadsheet formulas in every cell of operational CSV exports."""

import csv


def sanitize_csv_cell(value):
    if not isinstance(value, str):
        return value
    probe = value
    while probe and (probe[0].isspace() or ord(probe[0]) < 32 or probe[0] in {"\x7f", "\ufeff"}):
        probe = probe[1:]
    return "'" + value if probe.startswith(("=", "+", "-", "@")) else value


class SafeCsvWriter:
    def __init__(self, stream, **kwargs):
        self.writer = csv.writer(stream, **kwargs)

    def writerow(self, row):
        return self.writer.writerow([sanitize_csv_cell(value) for value in row])
