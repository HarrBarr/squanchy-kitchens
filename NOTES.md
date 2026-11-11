# Notes

## Time spent
- Roughly N hours. *(Fill in before submitting.)*
- Where it went: parser and rules engine with the golden test first, then the data model,
  ingest and API, then the Angular screens, then Docker, README and these notes.

## Decisions Summer didn't ask for, and why

- **Logger registry with dated assignments, unit (C/F) on the assignment.** The raw files
  only have time and temperature. Dated assignments handle "we moved one of the Tel Aviv
  loggers into the new display fridge last week" without anyone splitting files by hand.
  `assigned_to` includes that whole local day. TL-0417 is on the walk-in through 16 Sep
  23:45 and on Display 2 from 17 Sep 00:00
  ([`test_logger_move_splits_one_file_across_two_fridges`](backend/tests/test_ingest.py)).
  The unit lives here so Haifa is converted correctly and Fahrenheit is never guessed from
  how big the number is. If a file's `Units:` header disagrees with the registry, the
  import warns and still trusts the registry.
- **Registry edits re-file existing readings.** When Summer records a move after the files
  were already uploaded, readings from that date on move to the new fridge and the
  excursions are recomputed. Without this, a late registry entry would leave a week of data
  on the wrong fridge. The unit is *not* re-applied: changing the unit after import needs a
  re-upload.
- **One reading strictly above 5.0°C is a spike, not an alert.** Two or more consecutive
  readings are an excursion. `ERR`, a gap over 15 minutes, or a logger move breaks a run.
  Duration is the last minus the first reading of the run, not until recovery (Ashdod: 60
  min). Threshold, interval and the 2-reading minimum are environment variables; the
  defaults match the oracle.
- **Spikes are derived, not stored.** They aren't alerts and never go on the inspector
  document, so they're computed on the fly for the chart and the card footnote. The window
  is padded so a run crossing the edge of the period is judged on its full length.
  Excursions and gaps are stored.
- **The whole logger history is recomputed after each upload** instead of only the
  affected window. A run can span two weekly files, and a year of 15-minute readings is
  about 35k rows, so this is simpler and correct. It is the first thing to revisit if
  history grows to many years.
- **MySQL 8 in Docker Compose**, not SQLite or a host MySQL. The Ministry can ask about any
  past week, and the uploads will keep coming every week. MySQL runs as a Compose service
  (official image, named volume, healthcheck), so a reviewer still only needs Docker. 3306
  is not published, to avoid clashing with a local MySQL. The cost is a heavier stack than
  SQLite.
- **Original files are stored with their SHA-256, and readings upsert on (logger,
  timestamp).** Uploading the same file again is a no-op. A corrected file updates the
  readings, with a warning that says how many values changed, and the excursions are
  recomputed. The inspector may ask what was uploaded, not only what the chart shows now.
- **UTC in storage, Asia/Jerusalem on screen, DST included.** The files have no offset, and
  a fixed +3 would be wrong from the last Sunday of October. In the repeated autumn hour
  the first occurrence (summer time) wins, because the files give no way to tell the two
  apart. Two readings in that hour would collapse into one.
- **A row with a valid timestamp and a bad value is kept as a sensor error, not dropped.**
  The chart then shows a break instead of a silent hole. Lines without a readable timestamp
  are skipped and counted in the import summary.
- **Fridge card colours:** red = any excursion in the period, with an "Ongoing" badge when
  it hasn't recovered by the last reading. Amber = no excursion, but a gap or a sensor
  error. Green = everything else, isolated spikes included, with a quiet "n spikes"
  footnote. I added **grey** for "no readings in this period", so an empty week isn't shown
  as healthy.
- **A fridge still above the limit stays red until a newer file shows it recovered.** The
  dashboard opens on the newest week, and files arrive one at a time. Without this, a fridge
  that was still failing at its last uploaded reading (Rishon cream cakes, Be'er Sheva dairy)
  turned grey "awaiting upload" as soon as any other logger's next-week file came in. A
  missing file must never make a failing fridge look fine. The card keeps the "Ongoing"
  badge, and hovering its label shows "still above 5°C at last reading, Sun 20 Sep 23:45".
  Waiting fridges that were fine say "Awaiting this week's file", and an incomplete week has
  a banner linking to the previous complete one.
- **The dashboard defaults to the ISO week of the latest reading**, not "this week". The
  demo data is from September, and Summer looks at the week she just uploaded.
- **A small registry screen** lets her record a move or add a new logger, such as TL-9999,
  herself. The seed file isn't the only way in.
- **No email ingestion, no LLM or agent.** A file picker plus a logger dropdown is what she
  asked for. Reading her inbox would be a later convenience.
- **Visual theme from the Simple To Work brand directions ("Northern lights", Glow).** It is
  dark by default because Summer reads it on her phone, often in a dim back room. Status
  colours stay the brand's ok / warn colours plus the Sunset aurora red `#FF5C5C`, so "above
  5°C" is never confused with decoration. Only a fridge that is above the limit *right now*
  gets a glowing red temperature; a recovered fridge in a red week shows its healthy reading
  in plain text. Fonts are self-hosted (no Google Fonts call at runtime, except the Material
  Symbols icon font). The print stylesheet resets to ink on white for the inspector.
- **Tooling:** Angular 22 is the version `ng new` scaffolds today, and its default test
  runner is Vitest, so the frontend tests run in plain Node with no browser in the image.
  I used **npm** throughout instead of the pnpm in the plan, picked once and used
  consistently.

## Questions I would ask Summer before this goes live

- Is 5.0°C a strict upper limit for every fridge (dairy, cream cakes, walk-in, display),
  or do some units have a different threshold? Any freezers later?
- When a logger is moved, who updates the registry: only you, or also the branch manager?
  Should a file be rejected if its dates aren't covered by any assignment? (Today those
  rows are skipped with a warning, and the whole file is rejected if none fit.)
- How long must we keep readings and original files for the Ministry?
- Should isolated door-opening spikes appear on the inspector export at all, for example as
  a footnote, or stay off it entirely?
- If a fridge is mid-excursion when you check your phone on a Wednesday, do you want a
  notification, or is the weekly upload still the rhythm?
- When a manager sends a partial file and then a full one, is "latest file wins on
  overlapping timestamps" the right merge, or should we keep both and flag the conflict?
- Is the Haifa logger the only Fahrenheit device? Will new loggers ever use an interval
  other than 15 minutes?

## What's not done, and what I would do with one more hour

- Not done: PDF export (there's a print stylesheet instead), login, email ingestion,
  multi-week comparison, registry CSV import from the UI, notifications, a per-fridge
  threshold, and an end-to-end browser test.
- One more hour: a Playwright run of the clean-clone path (`docker compose up` → three red
  cards → open Rishon → download the CSV) in CI, so the release bar in the plan is checked
  automatically and not by hand.

## AI tools

*(Review and make this your own before submitting.)*

- One thing they got wrong or I rejected: an early version of the API test expected Ashdod's
  card to say "60 min", but the shared duration formatter renders 60 minutes as "1 h". The
  report and the CSV keep the exact `duration_minutes` column (60) next to the
  human-readable label, so the inspector always has the number.
- How I caught it: the API test failed. I also checked that the golden test pins
  `duration_minutes`, not the label.
- Where in the repo you can see that:
  [`backend/tests/test_api.py`](backend/tests/test_api.py) (`test_dashboard_defaults_to_latest_week_and_colours`)
  and [`backend/tests/test_excursions_golden.py`](backend/tests/test_excursions_golden.py).
- Guardrails written down before any code: the unit always comes from the registry, never
  from the size of a value (38.3 on the Haifa logger is °F), and `ERR` or a gap always
  breaks a run. Both are pinned by the golden test and
  [`backend/tests/test_rules.py`](backend/tests/test_rules.py).

## Approach
- Started from the email and the messy sample table. Wrote the parser and the rules against
  generated mock files with a known oracle, and made the golden test pass before building
  the three screens on top of a stable API.
