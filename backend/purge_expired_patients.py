"""Scheduled retention purge for the patient registry (name, phone, confirmed
Prakriti) - entries not seen (registered or looked up) within
PATIENT_RETENTION_DAYS (default 365, configurable via env var) days.

Run on a schedule (this process does NOT loop or self-schedule):
  Windows Task Scheduler: run `python purge_expired_patients.py` daily.
  cron: 0 3 * * * cd /path/to/backend && ./.venv/bin/python purge_expired_patients.py

This only removes patients-table rows - past visit records (sessions, audit
events, ABDM exports) are untouched; they are the clinical/legal record, not
the return-visit convenience registry this purge targets.
"""

import main


def run() -> None:
    purged = main.purge_expired_patients()
    print(f"Purged {len(purged)} patient registry entr{'y' if len(purged) == 1 else 'ies'} "
          f"past the {main.PATIENT_RETENTION_DAYS}-day retention window.")


if __name__ == "__main__":
    run()
