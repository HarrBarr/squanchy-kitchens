# Notes

## Time spent

- About 6 hours in total, with AI assistants (see [AI tools](#ai-tools)): about 1 hour of
  planning with Grok and about 5 hours of development. The commit timestamps span longer
  because I took breaks between commits.
- Where it went: planning the stack and architecture, and writing the development guide and
  the auth spec with Grok; then the parser, rules engine and golden test, data model, API,
  the three screens and Docker; fixes from using the app myself (dashboard week logic,
  ongoing fridges, drag and drop); the brand theme and the phone layout; sign-in, roles and
  the flag/void review; testing the phone flow end to end, removing secrets from the repo,
  the README and these notes.

## Decisions Summer didn't ask for, and why

**Data and rules**

- **A logger registry with dated assignments, and the unit (°C/°F) on the assignment.** The
  files only have time and temperature. Dated assignments handle "we moved a Tel Aviv logger
  into the new display fridge" without anyone splitting files: TL-0417's readings go to the
  walk-in through 16 Sep and to Display 2 from 17 Sep. The unit comes from the registry, never
  from the size of a value, so 38.3 on the Haifa logger is 3.5°C, not a disaster. Recording a
  move late re-files the readings already uploaded.
- **Two or more consecutive readings strictly above 5.0°C are an excursion; one is a spike.**
  She said a door opening is fine and a slowly warming fridge is not. `ERR`, a hole over 15
  minutes or a logger move breaks a run. Duration is first to last reading above the limit
  (Ashdod: 60 min). Spikes are shown on the chart, never on the inspector report. The
  threshold, interval and 2-reading minimum are settings; the defaults match the oracle
  (`backend/tests/test_excursions_golden.py`).
- **A bad value with a valid timestamp is kept as a sensor error,** so the chart shows a break
  instead of a silent hole. Gaps are never joined with a line.
- **Times are stored in UTC and shown in Asia/Jerusalem, DST included.** A fixed +3 would be
  wrong from the end of October.
- **Original files are kept with their SHA-256; readings upsert on (logger, timestamp).**
  The same file twice is a no-op; a corrected file wins and the excursions are recomputed.
  The inspector may ask what was uploaded, not only what the chart shows today.
- **MySQL 8 in Docker Compose**, not SQLite: the Ministry can ask about any past week, so
  this is a growing history. MySQL is a Compose service, so a reviewer still only needs
  Docker; its port is not published.

**Dashboard**

- **Card colours:** red = an excursion in the period ("Ongoing" if not recovered); amber =
  a gap, a sensor error, or this week's file not uploaded yet; green = everything else,
  door-opening spikes included; grey = a fridge that never had data.
- **It opens on the newest week with data.** After one early upload for a new week, the other
  fridges say "Awaiting this week's file" and a banner links to the last complete week. I
  found this by using the app: one W39 file made the whole dashboard look empty.
- **A fridge still above 5°C at its last upload stays red** until a newer file shows it
  recovered. A missing file must never make a failing fridge look fine.

**People and access** (spec: `squanchy-kitchens-auth.md`)

- **Two roles.** Summer (admin) sees everything; each branch manager signs in, uploads and
  exports only their own branch, instead of e-mailing files to her. Every rule is enforced
  on the API (live role and branch on each request; another branch is `403`, not an empty
  list). A manager's file with one reading outside their branch is refused whole.
- **Flag, review, void.** A manager flags their own upload as a mistake; only Summer voids.
  Voiding is a soft delete: the row, the readings and the original file stay, the data
  disappears from every view, excursions are recomputed, and the audit log says who and why.
  Voiding a *correction* brings back the earlier file's values.
- **No passwords or secrets in the repository.** Without configuration, the first start
  generates the sign-in passwords (printed once) and a JWT secret per install; reviewers get
  their passwords separately in a `.env`. The demo values in early commits are retired.
  The app listens on 127.0.0.1 only. No e-mailed password reset (it would need an SMTP
  account): Summer resets passwords on the Users screen.

**Look and feel**

- **Mobile first, in the Simple To Work "Northern lights" brand** (dark, since she reads it
  on her phone in a back room). "Above 5°C" uses a clear red, never a decorative colour, and
  only a fridge that is warm *right now* gets a red temperature. The printed report is dark
  ink on white. Drag and drop works anywhere on the page.
- **Not built:** e-mail ingestion and any LLM or agent. A file picker (or a drop) plus a
  logger choice is what she asked for.

## Questions I would ask Summer before this goes live

- Is 5.0°C the limit for every fridge (dairy, cream cakes, walk-in, display)? Any freezers
  coming?
- Who records a logger move: only you, or also the branch managers?
- How long must readings and original files be kept for the Ministry?
- Should door-opening spikes appear on the inspector export, for example as a footnote?
- If a fridge is warming up mid-week, do you want a notification, or is the weekly upload
  the rhythm?
- When a manager sends a partial file and then a full one, is "the latest file wins" right?
- Who may void a file: only you, or also the manager who uploaded it? Should a flagged file
  already be left off the inspector report, or only once voided (today)?
- Is the Haifa logger the only Fahrenheit one? Will any logger record more often than every
  15 minutes?

## What's not done, and what I would do with one more hour

- **Not done:** PDF export (there is a print layout), e-mail ingestion, notifications,
  per-fridge thresholds, multi-week comparison, a read-only inspector login, refresh tokens,
  and an end-to-end browser test in CI.
- **One more hour:** put the phone flow I tested by hand (manager uploads and flags, admin
  reviews and voids, at 390 px with real taps) into CI as a browser test, next to the
  clean-clone check (`docker compose up` → three red cards → CSV). The two worst bugs below
  were only found that way.

## AI tools

I used two AI tools, one for planning and one for building:

1. **Grok, for planning.** I had Grok read the assignment e-mail from my mailbox, then
   discussed the stack and the architecture with it: FastAPI + MySQL + Angular in Docker
   Compose, the logger registry, the alert rules, testing against a known answer. It then
   wrote the development guide,
   [`squanchy-kitchens-development.md`](squanchy-kitchens-development.md), as the brief.
   Later, a second discussion with Grok about sign-in, roles and reviewing uploads produced
   the auth spec, [`squanchy-kitchens-auth.md`](squanchy-kitchens-auth.md).
2. **Claude Code (CLI), for building.** It developed and tested the app from those two
   documents, and wrote most of the code and tests.

I set the direction, made the product decisions, used the app as Summer and as a branch
manager, asked for the changes, and checked the results.

- **One thing Claude Code got wrong:** the **Void** button did nothing. The click handler was named
  `void`, and in an Angular template `(click)="void(u)"` is the JavaScript `void` operator,
  not a method call (the formatter even rewrote it to `(void u)`). It compiled, the unit
  tests passed (they only checked who *sees* the button), and every click silently did
  nothing.
- **How I caught it:** I asked for the flag and void flow to be tested on a phone. A real
  browser at 390 px, tapping at screen coordinates, opened no dialog. The same run found a
  second bug: the confirmation message covered the phone's bottom navigation for 4 seconds
  after every action.
- **Where to see it:** commit `68a74c6`; the regression test
  [`frontend/src/app/uploads/uploads.spec.ts`](frontend/src/app/uploads/uploads.spec.ts)
  clicks the real Void, Dismiss and Flag buttons.
- **Other things I rejected or caught:**
  - Claude Code shipped demo passwords and a JWT secret as Compose defaults in this public repo, and
    first only hid them from the sign-in page. I had them removed (commit `c8ed28d`).
  - One early upload for a new week emptied the dashboard; I noticed while using it
    (commit `a66a46c`, regression test in `backend/tests/test_api.py`).
  - Two bugs passed on SQLite and failed on MySQL. Running the tests in the MySQL container
    caught them (commits `a55c95d`, `e4f103e`).
  - Its first theme painted a recovered fridge's healthy temperature red; a screenshot
    review caught it before it shipped.
  - A clean-clone test caught alembic importing a stub `app` package left in the image by
    the Docker dependency-cache layer. It only showed without the build cache (commit
    `ad7126a`).
  - Re-running the full suite to verify that fix exposed random 401s: PyJWT rejected tokens
    "issued in the future" after the VM clock jumped back a few seconds. Tokens now allow
    60 s of clock skew (commit `b3ce00a`).

## Approach

Assignment e-mail → planning discussion with Grok → development guide → build with Claude
Code. The sign-in and roles layer followed the same path: a discussion with Grok → the auth
spec → built with Claude Code. The build followed the guide's order: the parser and the rules first, against mock
files with a known answer (`data/expected_excursions.json`), with the golden test passing
before the screens were built on top of a stable API. After that I used the app as Summer and
as a branch manager, and had what got in the way fixed: the dashboard week logic, ongoing
fridges, drag and drop, the brand theme, the phone layout, sign-in and roles, and keeping
passwords out of the repo.
