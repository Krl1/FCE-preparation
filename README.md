# FCE Trainer

[Polski](README.pl.md) · **English**

A local browser app for preparing for the **Cambridge B2 First (FCE)** exam. It generates tasks
(**Use of English** + **Writing**), marks your answers — including ones **pasted from elsewhere**
(a coursebook, your tutor) — and keeps a **log of your own mistakes**, which then steers what you
get next, so you unlearn the errors you actually repeat.

> ### ⚠️ Read this before you run it
>
> This is a **personal, locally-run tool**, not a service for multiple users. A few consequences
> you need to know **before** the first start:
>
> - **The app has no authentication whatsoever.** Anyone who can reach the port has full access to
>   your mistake log and can spend your Claude subscription. That is why `compose.yaml` binds the
>   port to **`127.0.0.1` only** — do not change it to `0.0.0.0` without putting something in front.
> - **The Docker setup mounts `~/.claude` writable**, which hands the container your **Claude
>   subscription credentials** (it has to: Claude Code refreshes an expiring token). Only run this
>   image from code you trust, and never publish the built image — it is derived from your home
>   directory.
> - **Model calls count against your subscription limits** (Pro/Max), not against a separate API key.
> - **`data/fce.db` is your personal data** — mistake log, submissions, statistics. It is in
>   `.gitignore` and must never reach a repository. The same goes for the import source files
>   (see *Importing past mistakes*).

## How it works

- **Backend:** FastAPI (Python) + SQLite.
- **Model:** the app shells out to **Claude Code in headless mode** (`claude -p … --output-format json`)
  and uses your **subscription login** (`~/.claude/.credentials.json`) — **no API key**. The whole
  dependency lives in one file: `app/llm_client.py`.
- **Frontend:** a static page (HTML/JS/CSS, no frameworks) with five views: *Practice tasks*,
  *Practice mistakes*, *Check external*, *My mistakes*, *Statistics*.
- **Language:** the **PL / EN** switch in the top-right corner changes both the interface and the
  language of what the model produces (instructions, explanations, feedback) — handy when you show
  the app to an English speaker. The choice is remembered (localStorage); Polish is the default.
  Note: mistakes logged earlier keep the language they were written in.

## Requirements

- Python 3.12
- Claude Code installed and **logged in** (`claude` on your `PATH`). Check with `claude --version`.

## Installing dependencies

```bash
pip3 install --user --break-system-packages -r requirements.txt
```

(Or, if you have `python3-venv`: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`,
then run through `.venv/bin/python -m uvicorn …`.)

## Running

```bash
python3 -m uvicorn app.main:app --reload
```

Then open **http://localhost:8000**.

## Importing past mistakes (optional)

If you already have a list of your errors — from lessons, marked writing, or your own notes — you
can load it into the log up front, so the app aims at your weak spots from the very first task.
The script reads three files from the project root:

| File | Format | How it is processed |
|---|---|---|
| `english_mistakes.tsv` | TSV: `date`, `wrong`, `correct`, `category`, `note`, `source` | deterministically, mapping `category` onto the FCE taxonomy (`CATEGORY_MAP` in `app/import_mistakes.py`) |
| `writing_mistakes.txt` | free-form text | the model extracts "wrong → correct" pairs; entries get the `writing` type |
| `other_mistakes.txt` | free-form text | same as above, type `imported` |

**These files are not in the repository — and should not be.** They are personal material, so they
are listed in `.gitignore`. Format templates to copy live in `examples/`:

```bash
cp examples/english_mistakes.tsv examples/writing_mistakes.txt examples/other_mistakes.txt .
# replace the contents with your own, then:
python3 -m app.import_mistakes
```

A missing file is simply skipped — use one, two, or none. The import is **idempotent**: each source
writes entries tagged `import:<filename>`, and a re-run first deletes the previous entries from that
file and inserts fresh ones. Running it again does not multiply duplicates, even though the model's
extraction is not deterministic.

Note: the text files go through the model, so importing them **costs subscription calls** (the TSV
does not — it is parsed locally).

## Using the app

- **Practice tasks** — pick a task type (e.g. *open cloze*, *key word transformation*, *essay*),
  optionally a topic (or leave it to be chosen automatically from your mistakes), generate and solve.
  The app marks your answer and **proposes** mistakes for the log — nothing is written until you
  confirm (see *The life of a mistake*).
  **Every Use of English part gives you 5 items per click**, checked with one button — you get
  a score (e.g. 3/5) and a comment on each item:
  - *Part 1 (multiple-choice cloze)* — one coherent text with 5 gaps, each with 4 options; for the
    wrong ones you get a walkthrough of all options,
  - *Part 2 (open cloze)* — 5 sentences, one one-word gap each,
  - *Part 3 (word formation)* — 5 sentences with a base word to transform,
  - *Part 4 (key word transformation)* — 5 rewrites with a given key word.

  The item count is the `ITEMS_PER_EXERCISE` constant in `app/llm_client.py`. Closed answers
  (options) are marked **deterministically** by the server; for open answers the model marks, but
  an exact match against the key always counts as correct — a good answer will not land in the log
  as a mistake.
  Tasks are generated **in batches**: one model call creates several exercises, you get the first
  immediately and the rest wait in a queue in the database, appearing **instantly** on later clicks.
  Because the cost of a call is dominated by the fixed headless overhead (~23k tokens regardless of
  content), this is several times cheaper and faster. Batch size: `_UOE_BATCH` / `_WRITING_BATCH`
  in `app/llm_client.py`.
- **Practice mistakes** — focus mode: the app shows one of your mistakes (picked at random, weighted
  by how often your weak topics come up) together with its explanation, and generates a **set of
  5 exercises** for it. Buttons: *Exercise* (another set for the same mistake), *Another mistake*
  (switch to a new one). Under the explanation you also get **I disagree** (object to the
  explanation) and **Delete mistake** — you deal with a mistake where you see it, without hunting
  for the entry in the log.
  At the top there is a **Daily goal** — how many mistakes you want to clear per day. A mistake
  counts (+1) only after **5 correctly solved exercises** for it, counted **cumulatively within the
  day** — 3/5 in one go and 2/5 later also does it. Progress shows under the goal ("Correct
  exercises needed for this mistake: 3/5"). The threshold is `DRILL_CORRECT_TARGET` in
  `app/main.py`. Next to the goal is your **streak** (🔥) — consecutive days with the goal met.

  **A missed day can be made up.** Sleeping through a day does not break the streak immediately: the
  next day has to cover the goal for itself and for every missed day — after one missed day that is
  `2 × goal` distinct mistakes, after two `3 × goal`. The counter above the bar then shows this
  raised goal, and a warning appears under the streak ("⚠️ 2 missed days — clear 15 different
  mistakes today or the streak is gone"). The rules:
  - **three days in a row without practice = the streak breaks** irreversibly (`GRACE_DAYS` in
    `app/streak.py`);
  - settlement is **all or nothing** within a day — 10 out of the required 15 does not reduce
    tomorrow's debt; such a day simply counts as an ordinary completed day and starts a new streak;
  - **made-up days do not enter the counter** — after two missed days and repayment the streak grows
    by 1, because 🔥 shows days you genuinely practised;
  - today always has until midnight — while it lasts the streak holds (though flagged at risk)
    rather than resetting at 00:00.

  A note on scale: at a goal of 5 mistakes a day that means 25 correct exercises — and with a
  two-day backlog, 15 mistakes, i.e. 75 exercises in one day. If that is too much, lower the
  *Daily goal* (the streak rule always uses the current goal value).

  The **Individual mistakes / Groups** switch decides what you get to work on. Group mode
  lets you move faster through many related slips: instead of a single sentence the model
  sees the rule and several contexts you broke it in. A group counts as **one mistake**
  toward the daily goal, so the 🔥 streak stays comparable between modes.
- **Flashcards** — a fast sweep through many rules at once. A card is built from what your
  journal already holds (wrong → right, or a group's rule with its contexts), so it appears
  instantly and costs no model call. You reveal the answer and grade it **I know it** or
  **I don't** — with the space bar and `n`, without reaching for the mouse.

  Every card carries **its own review date**: known → back in 1, 3, 7, 14, 30, 90 days;
  not known → back tomorrow. A card you have never got right once comes back the same day —
  the ladder only starts once you have recalled it correctly. A session shows only what is
  due today plus new cards up to a daily limit (20 by default) — without that limit the
  first session would hold two hundred items. This is the one place in the app where
  material **expires**: in the journal a mistake stays forever, on a flashcard a mastered
  rule moves further away.

  Flashcards **do not feed the 🔥 streak or the daily goal** — they have their own counter.
  The streak measures five correct exercises per mistake, while a card is a single click;
  mixing the two would devalue the former. A card you get wrong four times is marked as
  stubborn and offers a jump to *Practice mistakes* — if recall alone is not working,
  exercises are. The **Improve this card** button is the only one that calls the model: it
  turns the wrong → right pair into a gapped sentence, once and for all.
- **Check external** — paste a task from a book along with your answer; the app marks it and proposes
  mistakes for you to confirm.
- **My mistakes** — an overview of *Weak points* and the full *Mistake log*. Each entry has
  **Practice this mistake**, which jumps to *Practice mistakes* with that entry and generates an
  exercise straight away, and **Delete mistake** (with in-place confirmation), which drops it
  from the log.

  The **Entries / Groups** switch shows the same log in two views. A group is one rule
  together with the contexts you broke it in — **Merge new** assigns entries that have no
  group yet, and **Regroup everything** recomputes the split from scratch (it discards
  manual edits and any empty groups you chose to keep, so it asks for confirmation). Groups
  may span topics when the entries break the same rule. **Contexts** expands a group to the
  entries behind it, where **Detach** returns a single entry to the unassigned pool;
  **Rename** fixes the rule's name. **An empty group stays** — when you
  remove its last entry the app asks whether to delete the group too; a rule with no
  entries can still be practised.
- **Statistics** — two sections: *Learning* (exercises generated, answers checked, accuracy, reviews,
  mistakes logged, breakdown by task type) and *Claude usage* (call count, input/output/cache tokens,
  **estimated cost at API rates**, and a breakdown by call type).
  Usage statistics are collected **from now on** (from the JSON envelope of each `claude` call);
  they do not cover earlier calls (imports, tests). **Note:** headless mode carries the overhead of
  Claude Code's system prompt (tens of thousands of cache tokens per call), so the estimated cost is
  an **upper bound** — the same app on an API key with a lean prompt would use noticeably less. That
  is why an **API estimate without the overhead** is shown alongside (real prompt + response only,
  priced by the model's rates — the model used, and a cheaper one: Sonnet 5), which gives a more
  realistic number for deciding whether to migrate to the API. Rates live in `app/pricing.py`; if
  a model has no **confirmed** rate, the estimate is clearly marked as assumed rather than presented
  as fact.

### The life of a mistake: nothing enters and nothing leaves on its own

**Marking does not write mistakes to the log.** It returns them as **proposals** — each has an
**Add to log** button, and above the list sits a reminder bar with (when there is more than one)
**Add all**. In multi-item tasks the button sits next to the gap the mistake came from; proposals
not tied to any gap go into a separate section so nothing disappears quietly. What *is* saved is the
**attempt** (for accuracy statistics), regardless of what you confirm.

The reasoning: confirming three accurate entries is easier than later digging ten junk ones out of
the log. Side effects worth knowing: *Weak points*, topic selection and the "Mistakes logged"
counter see **only confirmed** mistakes, and a proposal's topic is normalised to the taxonomy at
marking time — you confirm exactly what will be stored (the server normalises it again on write,
because data from the browser is not trustworthy).

Objecting (**I disagree**) applies to entries that **are** in the log — a proposal does not need to
be challenged, you can simply not confirm it.

Once logged, a mistake **stays in the log forever** — there is no automatic retirement after n
repetitions. The `reviews` table only records that you cleared a mistake toward the goal on a given
day, and it **does not affect selection**: `_choose_focus_error` weighs only the count and recency of
entries in a topic. Practical consequence: a mistake you have mastered ten times can come back in
*Practice mistakes* as often as a fresh one.

So you keep the log tidy **by hand**:

- in *My mistakes* — the **Delete mistake** button on every entry,
- in *Practice mistakes* — the same button **on the mistake you are currently drilling**, so you do
  not have to find it later among hundreds of others.

Both require confirmation (**Yes, delete / Cancel**), deliberately without a browser dialog.
Deleting **does not undo the goal or streak you earned today** — reviews stay in `reviews`, because
work you genuinely did should stay counted. What does change is the *Weak points* list, since it is
computed from the log on the fly.

### Objecting to an explanation ("I disagree")

The model sometimes gets the explanation itself wrong — for instance quoting a word that was never
in the task. So every explanation (a comment on a gap, a walkthrough of an option, an entry in the
mistake log) carries an **I disagree** link. It opens a comment field — say what is wrong — and
sends the objection for re-checking together with **the exact task text and your answers**, so the
model can verify whether it invented the quote.

The re-check decides **two independent things**, because conflating them was a source of bad
verdicts:

1. **Whether the explanation was wrong** (`verdict`: `upheld` / `rejected`) — an invented quote is
   enough to uphold the objection, even if the grammar rule itself was true.
2. **Whether your answer was acceptable after all** (`student_was_right`) — a separate matter. The
   most common case: the explanation was faulty but the answer still wrong.

What happens next:

- **Objection accepted** → you get a **corrected explanation** (immediately, with no data changes).
- **The model additionally concedes your answer was acceptable** → an **Apply correction** button
  appears. Only clicking it removes the faulty entry from the log and recomputes the attempt's score.
  Nothing changes without your confirmation, and every objection is recorded in the `disputes` table
  (applied once).
- **Objection rejected** → the explanation stands, with reasons. The prompt explicitly forbids
  conceding out of politeness — otherwise you could talk your way out of every real mistake and the
  log would stop being trustworthy.

## Running in Docker (with autostart when the laptop boots)

One-off:

```bash
docker compose up -d --build
```

The app is then available at **http://localhost:8008**.

### How autostart works

The container has the `restart: unless-stopped` policy, and the Docker daemon is enabled in systemd
(`systemctl is-enabled docker` → `enabled`). When the laptop boots, the daemon starts and resumes the
container if it was running when the machine was shut down. Two behaviours worth remembering:

- `docker compose stop` (or `docker kill`) is **a stop you asked for** — after it the container will
  not come back on its own, not even after a system restart. Resume it with `docker compose start`.
- If you would rather it always came back, even after a manual stop, change the policy in
  `compose.yaml` to `restart: always`.

### What is mounted and why

The image **does not contain** Claude Code — the binary and the configuration are mounted from the
host, so the container uses your subscription login and needs no API key:

| Mount | Mode | Why |
|---|---|---|
| `./data` | write | the SQLite database (mistake log, progress, statistics) stays on the host |
| `~/.local/bin/claude` + `~/.local/share/claude` | read | the native Claude Code binary (updating on the host takes effect after a container restart) |
| `~/.claude` | **write** | credentials; Claude Code refreshes an expiring token, so mounting read-only would break authorisation once it expires |

#### Why the paths inside the container match the host

`~/.local/bin/claude` is an **absolute** symlink (→ `/home/<user>/.local/share/claude/versions/X.Y.Z`).
If the container mounted those directories at a different path, the symlink would point at nothing
and `claude` would not start. That is why the home directory in the image equals the host's
`${HOME}` — `compose.yaml` passes it in as the `APP_HOME` build argument. No username is hardcoded
anywhere in the code.

For the same reason the container runs as UID/GID **1000**: it has to read
`~/.claude/.credentials.json` (mode 0600) and write the database in `./data`. If your user has a
different UID (check with `id -u`), build like this:

```bash
export APP_UID=$(id -u) APP_GID=$(id -g)
docker compose up -d --build
```

### Everyday commands

```bash
docker compose logs -f          # follow the logs
docker compose ps               # container state and health
docker compose up -d --build    # after a code change: rebuild and resume
docker compose stop             # stop (will not come back on its own)
docker compose start            # resume
docker compose down             # remove the container (data in ./data stays)
```

### Things worth knowing

- **Do not run the container and a host `uvicorn` at the same time** — both would write to the same
  SQLite database from two processes, risking "database is locked" errors.
- The port is published **on `127.0.0.1` only**. The app has no authentication and uses your
  subscription, so it should not be visible to other devices on the network.
- The container also writes to `~/.claude` (refreshed token, call history) — it shares that directory
  with your interactive Claude Code. Calls from the app count against the same subscription limits.
- To verify after the next laptop restart: `docker compose ps` should show `Up ... (healthy)`.

## Tests

```bash
python3 -m pytest -q
```

Coverage: the database layer (including a concurrency regression and queue migrations), task
selection logic (`srs`), the streak rule with backlog repayment (`streak` — the module is pure, so
the tests build day histories without a database), parsing of model responses and deterministic gap
marking, the HTTP endpoints (FastAPI TestClient, without calling the model), and importing past
mistakes.

There is also a browser-free frontend walkthrough (a DOM and `fetch` stub) that visits every tab and
checks that no path blows up on an exception:

```bash
node tests/smoke_frontend.js
```

## Configuration (environment variables)

- `FCE_CLAUDE_BIN` — path to the `claude` binary (default: `claude`).
- `FCE_LLM_TIMEOUT` — model call timeout in seconds (default: 180).
- `FCE_DB_PATH` — path to the SQLite database file (default: `data/fce.db`).

## Notes

- Model calls **count against your subscription limits** (Pro/Max). For personal study that is
  usually immaterial.
- Well-formed JSON is enforced by the prompt and parsed with one retry (not guaranteed by a schema).
- A single check usually takes ~2–5 s (a loading indicator is shown).
- To move to an **API key** later, it is enough to swap the `_invoke` function in `app/llm_client.py`.

## License

[MIT](LICENSE) — do what you like with it, just keep the copyright notice. No warranty.

This app is a study tool, not an official Cambridge Assessment English product. "B2 First" and "FCE"
are trademarks of their respective owners and are used here descriptively only.
