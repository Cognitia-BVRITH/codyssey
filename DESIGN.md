Codyssey — Design Document 

> This is the original proposal. Current contracts use snake_case fields, exact
> commits, and argument arrays; examples below are historical. For implemented
> behavior use docs/ARCHITECTURE.md and docs/VALIDATION.md. The initial validator
> creates a fresh checkout/container per invocation, replacing the proposed
> `git checkout .` reset. Cancellation and total-run deadlines remain pending.

# 1. Introduction and overview 

Codyssey is a Python tool that takes a GitHub issue and a repository, then tries to produce a bug fix that is verified by the project's own tests. It does this by finding the buggy code, asking an LLM to write a patch, running the tests in an isolated Docker sandbox, and retrying with the error output until it succeeds or hits a hard limit. 

# 1.1 Problem 

Fixing a bug in a large codebase is slow mostly because of finding the bug. A developer reads the issue, searches files, reads tests, makes a change, runs the tests, and repeats. Codyssey automates that loop. Its input is plain text (the issue) plus a codebase; its output is a patch (a diff file that can be applied with git apply) and a report showing whether the tests passed. 

# 1.2 Goals 

- Fix real issues at repository level, meaning the bug may be in any file, not just one pasted snippet. 

- Only call a fix "verified" when tests pass in a clean sandbox: the failing tests now pass and the previously passing tests still pass. 

- Stay inside a budget: a maximum number of attempts, tokens, and wall-clock time per issue. 

- Record every step so a failed run can be analyzed, not just counted. 

- Work with several LLM providers behind one interface, so free and paid models can be swapped by changing a config value. 

# 1.3 Non-goals 

- Training or fine-tuning a model. Codyssey only makes API calls to existing LLMs. 

- Beating the top leaderboard systems. The target is a working, measurable pipeline. 

- Fixing bugs in repositories that have no tests (v1 relies on tests as the success signal). 

- Automatically merging or pushing code. Codyssey produces a patch; a human decides what to do with it. 

# 1.4 Scope of version 1 

- Python repositories using pytest, evaluated on a small subset (20 to 50 tasks) of SWEbench Lite, a public set of 300 real GitHub issues with tests that decide success. 

- Interfaces: a command-line tool, a small REST API, and a simple web dashboard. 

- Java/Spring Boot repositories are a possible later extension, not part of v1. 

# 1.5 Glossary 

- | Term | Plain meaning | 

- | --- | --- | 

- | Repository (repo) | The folder of source code tracked by Git | 

- | Issue | A written bug report on GitHub | 

- | Patch / diff | A file describing exact line changes to code | 

- | LLM | Large language model, the AI that reads text and writes text or code | 

- | Agent | A program that calls an LLM in a loop and lets it use tools (read a file, run a test) | 

- | Localization | Working out which files and functions contain the bug | 

- | Sandbox | A disposable, isolated environment where untrusted code can run safely | 

- | Docker container | A lightweight isolated mini-computer started from a saved template called an image | 

- | API | A set of rules that lets one program ask another program to do something | 

| REST API | An API where you send HTTP requests (like GET or POST) to URLs and get JSON back | 

| Token | A chunk of text (roughly 3/4 of a word) that LLM providers use to measure input, output, and price | 

| FAILTOPASS tests | Tests that fail before the fix and must pass after it | 

| PASSTOPASS tests | Tests that pass before the fix and must still pass after it | 

# 3. Data design 

Codyssey stores small structured records in a SQLite database and large files (patches, logs, test output) on disk. SQLite is a database that lives in a single file with no server to install, which suits a student project. Python includes it in the standard library (sqlite3), and an ORM such as SQLAlchemy can sit on top. 

# 3.1 Core entities 

One task (an issue plus a repo) can have many runs (one execution of the pipeline), and each run has many attempts (one patch tried and tested). In database terms, each child row holds a foreign key, a column that points at the id of its parent row. 

| Entity | Purpose | Main fields | 

| --- | --- | --- | 

| Task | The bug to fix | id, repourl, basecommit, issuetitle, issuebody, testcommand, failtopass (list), passtopass (list) | 

| Run | One execution of the pipeline on a task | id, taskid, llmprovider, llmmodel, config (JSON), status, startedat, finishedat, totaltokens, totalcostusd | 

| Attempt | One patch generated and tested | id, runid, attemptno, suspectfiles (list), patchpath, teststatus, errorsummary, tokensin, tokensout | 

| TestResult | Outcome of one test in one attempt | id, attemptid, testname, group (FAILTOPASS or PASSTOPASS), outcome, durations | 

| LLMCall | Log of one request to a model | id, runid, stage, promptpath, responsepath, tokensin, tokensout, latencyms | 

| RepoIndex | Cached code map of a repo at a commit | id, repourl, commit, indexpath, builtat | 

# 3.2 Status values 

-   Run status: queued, running, verified (tests pass), failed (budget or attempts exhausted), error (infrastructure problem, such as Docker not starting). 

-   Attempt teststatus: patchinvalid (the diff would not apply), testsfailed, testspassed, timeout. 

# 3.3 File layout on disk 

Large or text-heavy data stays out of the database. The database stores the path instead. 

text data/ codyssey.db                      # SQLite database repos/<repo>@<commit>/           # cloned repository at the base commit indexes/<repo>@<commit>.json     # code map (classes, functions, line ranges) runs/<runid>/ config.json                    # exact settings used attempt1/ prompt.txt                   # what was sent to the LLM response.txt                 # what came back patch.diff                   # the proposed change testoutput.txt              # raw sandbox output attempt2/ ... finalpatch.diff               # only written when status = verified 

report.json                    # summary for the UI 

3.4 Example records 

A task input (JSON is a text format for structured data, written as key: value pairs): 

json { "id": "exampleproj-1234", "repourl": "https://github.com/example/proj", "basecommit": "a1b2c3d", "issuetitle": "Crash when username contains a space", "issuebody": "Calling createuser('john doe') raises KeyError ...", "testcommand": "pytest -x -q", "failtopass": ["tests/testusers.py::testspaceinname"], "passtopass": ["tests/testusers.py::testcreateuser"] } A finished attempt record: json { "runid": "r0007", "attemptno": 2, "suspectfiles": ["proj/users.py"], "patchpath": "data/runs/r0007/attempt2/patch.diff", "teststatus": "testspassed", "tokensin": 18400, 

"tokensout": 650 

} 

# 3.5 Data rules 

-   Immutable logs: prompts, responses, and test output are written once and never edited, so any run can be replayed or audited. 

-   Reproducibility: every run stores its config (model, temperature, limits) so the result can be reproduced. 

- No secrets in storage: API keys are read from environment variables and are never written to the database, logs, or prompts. 

-   Cache by commit: a repo index is keyed by repo@commit, so the same repo state is never indexed twice. 

# 4. Interface design 

An interface is the agreed way two parts talk to each other. Codyssey has five: a command line for developers, a REST API for the dashboard, and three internal interfaces that keep the LLM provider, the agent's tools, and the sandbox swappable. 

# 4.1 Command-line interface (CLI) 

Built with Python's typer (or argparse). A CLI is a program you run by typing commands in a terminal. 

bash 

Fix one issue from a GitHub URL 

codyssey fix https://github.com/example/proj/issues/1234 --model gemini-flash --maxattempts 5 

Fix a prepared benchmark task 

codyssey fix --task exampleproj-1234 

Run a batch of benchmark tasks and print a summary 

codyssey bench --tasks tasks.txt --limit 30 

Look at past results 

codyssey runs list 

codyssey runs show r0007 

| Option | Meaning | Default | 

| --- | --- | --- | 

| --model | Which configured LLM to use | from config.yaml | 

- | --max-attempts | Patch attempts before giving up | 5 | 

- | --max-tokens | Total token budget for the run | 300000 | 

- | --timeout | Wall-clock limit in minutes | 20 | 

- | --no-sandbox | Skip test execution (patch only) | off | 

4.2 REST API (backend for the dashboard) 

A REST API is a web server that answers HTTP requests. The client sends a request such as POST /runs and the server replies with JSON. We use FastAPI, a Python web framework that turns Python functions into endpoints and validates input automatically. This is the Python equivalent of the controller layer you would write in Spring Boot. 

| Method and path | What it does | Response | 

- | --- | --- | --- | 

| POST /runs | Start a run from an issue URL or task id | { "runid": "r0007", "status": "queued" } | 

- | GET /runs | List runs, newest first | array of run summaries | 

- | GET /runs/{id} | Run details and attempts | run object | 

- | GET /runs/{id}/events | Live progress stream (Server-Sent Events) | stream of event objects | 

- | GET /runs/{id}/patch | Download the final patch | .diff file | 

- | POST /runs/{id}/cancel | Stop a running job | { "status": "cancelled" } | 

- | GET /models | List configured LLMs | array of model names | 

- | GET /health | Check the server and Docker are up | { "ok": true } | 

Example request body for POST /runs: 

json 

{ 

"issueurl": "https://github.com/example/proj/issues/1234", 

"model": "gemini-flash", 

"maxattempts": 5 

} 

Errors use standard HTTP codes with a consistent body: 400 bad input, 404 unknown run, 429 provider rate limit reached, 500 internal error, each as { "error": "message" }. 

4.3 LLM provider interface 

Every model sits behind one Python class, so the pipeline never cares which company's model it is talking to. This is the adapter pattern: one common shape, one small adapter per provider. 

python 

from abc import ABC, abstractmethod 

from dataclasses import dataclass 

@dataclass 

class LLMResponse: 

text: str tokensin: int tokensout: int latencyms: int 

class LLMClient(ABC): 

@abstractmethod 

def complete(self, system: str, messages: list[dict], 

maxoutputtokens: int = 2000, temperature: float = 0.0) -> LLMResponse: 

"""Send a prompt, return text plus token counts.""" 

Implementations: OpenAICompatClient (one class covers every provider that offers an OpenAI-style endpoint, by changing baseurl and the key), GeminiClient, and OllamaClient (local models). A wrapper adds retry with exponential backoff (wait 1s, 2s, 4s...) when a provider returns a rate-limit error. 

4.4 Tool interface (what the agent can do) 

A tool is a function the pipeline lets the LLM request, such as "show me this file." The LLM replies with a tool name and arguments; Codyssey runs the function and sends back the result. 

| Tool | Arguments | Returns | 

| --- | --- | --- | 

| searchsymbol | name (class, function) | file, line range, signature | 

| searchtext | pattern, optional path | matching lines with file and line number | 

| readfile | path, startline, endline | the code lines | 

| listtests | path | test names in a file | 

| showcallers | function name | functions that call it | 

All tools are read-only. Only the validator can apply a patch, which stops the model from changing files in unexpected ways. 

# 4.5 Sandbox interface 

python 

class Sandbox: 

def start(self, image: str, repopath: str) -> None: ... 

def applypatch(self, diff: str) -> ApplyResult: ... 

def runtests(self, command: str, timeouts: int) -> TestReport: ... 

def reset(self) -> None: ...      # discard changes, back to the base commit 

def stop(self) -> None: ...       # destroy the container 

The orchestrator only uses this class. The Docker details stay inside one file, so the sandbox can later be replaced (for example by a cloud sandbox) without touching the rest of the code. 

# 5. Component design 

Each component is a Python module with one job. The Orchestrator calls the others in order, so each piece can be tested and replaced on its own. 

# 5.1 Orchestrator (the control loop) 

Job: run the whole pipeline for one task and decide when to stop. 

text function fix(task): prepare environment, run tests once to confirm the bug reproduces index = RepoIndexer.build(task.repo) suspects = Localizer.find(task.issue, index) context = Retriever.gather(suspects, task) feedback = none for attempt in 1..maxattempts: if BudgetGuard.exhausted(): break patch = PatchGenerator.propose(task.issue, context, feedback) result = Validator.check(patch) save attempt to database if result.passed: return VERIFIED(patch) feedback = result.errorsummary Sandbox.reset() return FAILED(bestattemptsofar) 

Codyssey v1 follows a fixed pipeline (localize, retrieve, patch, validate) rather than letting the LLM wander freely. It is cheaper, easier to debug, and its steps can be measured one by one. 

# 5.2 Repo Indexer 

Job: build a map of the code so searching is fast and structured. 

- Parses every .py file with Python's built-in ast module (an AST, abstract syntax tree, is the tree structure showing classes, functions, and their line ranges). 

- Stores: file, class, function, line range, docstring, and which functions call which. 

- Result is cached per repo@commit (see Data design). 

# 5.3 Localizer 

Job: answer "which files and functions probably contain the bug?" before any patch is written. 

1.  Keyword search: pull identifiers and error messages out of the issue and match them against the index. 

2.  Ranking: send the top candidates (names and signatures only, not full code) to the LLM and ask it to rank the most likely suspects. 

3.  Test-based signal (optional): run the failing test with coverage and list the lines it executes; code touched by the failing test is a stronger suspect. 

Output: a ranked list of 3 to 5 suspect functions with a confidence note. 

# 5.4 Context Retriever 

Job: assemble the right amount of code for the LLM to read, since LLMs have a limited context window (the maximum text they can read at once) and every token costs money or free quota. 

- Full source of the top suspects. 

- Callers and callees of those functions (one hop). 

- Existing tests that touch them. 

- Truncates to a token limit, dropping the lowest-ranked pieces first. 

# 5.5 Patch Generator 

Job: ask the LLM for a fix and turn the answer into a valid patch. 

- Prompt contains: the issue, the suspect code with line numbers, the relevant tests, and, on retries, the previous patch plus the test error. 

- The LLM is asked to reply with exact SEARCH and REPLACE blocks (the old lines and their replacement), which are more reliable than asking it to write a raw diff. Codyssey converts these to a standard .diff. 

- Rejects empty patches, edits to test files, and patches identical to an earlier attempt. 

# 5.6 Sandbox Runner 

Job: run code safely, using Docker. 

- One container per task, started from a prepared image (right Python version, dependencies installed, repo at the base commit). 

- Network disabled while tests run; CPU, memory, and process limits set; runs as a non-root user. 

- Each test command has a timeout and is killed if it exceeds it. 

- reset() runs git checkout . so a failed patch never leaks into the next attempt. 

- Controlled from Python through the Docker SDK (docker package). 

# 5.7 Validator 

Job: decide whether a patch really fixes the bug. 

1.  Apply the patch (git apply); if it fails, report patchinvalid right away. 

2.  Run the FAILTOPASS tests; all must pass. 

3.  Run the PASSTOPASS tests; none may break. 

4.  Re-run any failing test once to detect flaky tests. 

5.  Condense the output into a short errorsummary (last failing assertion, traceback tail) so the next prompt stays small. 

A patch is marked verified only when steps 2 and 3 both pass. 

# 5.8 Budget Guard 

Job: stop runaway cost and loops. 

- Tracks tokens used, attempts made, and elapsed time against the limits in the run config. 

- Stops the run when any limit is reached, and also when two attempts produce the same patch. 

- Pauses and retries when a provider returns a rate-limit error, which matters most on free tiers. 

# 5.9 Reporter 

Job: write report.json and the final patch, and feed live events to the dashboard. It reads from the same stored attempt records, so the CLI and the dashboard always show the same numbers. 

# 5.10 Error handling 

| Failure | Behaviour | 

| --- | --- | 

- | LLM rate limit (429) | Wait with exponential backoff, then retry; switch to a fallback model after 3 failures | 

| LLM returns malformed output | Re-ask once with a format reminder, otherwise count as a failed attempt | 

| Patch does not apply | Counts as an attempt; error is fed back to the LLM | 

| Docker unavailable | Run ends as error, not failed, so infrastructure faults are not counted as model failures | 

| Test timeout | Attempt marked timeout; the prompt tells the LLM its change may have caused an infinite loop | 

# 6. User interface design 

The dashboard is a single-page web app that talks to the REST API in section 4.2. It has three screens. The frontend is built with React (a JavaScript library for building pages from reusable components) and Vite (a tool that runs and bundles the app). If time is short, Streamlit (a Python library that builds dashboards without any JavaScript) is a faster fallback; it would poll GET /runs/{id} every 2 seconds instead of using live events. 

# 6.1 Screen map 

Home (submit and history) leads to Run Detail (live progress and result). Benchmark Summary shows aggregate results across many runs and links back to individual runs. 

6.2 Home screen: submit an issue and see history 

text 

+------------------------------------------------------------+ 

|  CODYSSEY                       [Home] [Benchmark]          | 

+------------------------------------------------------------+ 

|  Fix a bug                                                  | 

- |  GitHub issue URL: [ https://github.com/org/repo/issues/1 ] | 

|  Model:  [ Gemini Flash v ]   Max attempts: [ 5 ]           | 

|                                       [ Start run ]         | 

+------------------------------------------------------------+ 

- |  Recent runs                                                | 

- |  ID      Issue                    Model     Status    Time  | 

- |  r0007  Crash on space in name   gemini    VERIFIED  3m12s | 

- |  r0006  Wrong date format        groq      FAILED    8m40s | 

- |  r0005  Null pointer in parser   gemini    RUNNING   1m05s | 

+------------------------------------------------------------+ 

- Input checks: the URL must match the GitHub issue pattern, and attempts must be between 1 and 10, otherwise an inline red message appears. 

- Status values are colour-coded and also written as text, so colour is never the only signal. 

6.3 Run Detail screen: live progress and result 

text 

+------------------------------------------------------------+ 

- |  Run r0007  - Crash on space in name        [ Cancel ]     | 

- |  Status: RUNNING   Attempt 2 of 5   Tokens: 41k / 300k      | 

+------------------------------------------------------------+ 

- |  Pipeline                                                   | 

- |  [x] Reproduce bug   [x] Localize   [x] Retrieve            | 

- |  [>] Patch (attempt 2)   [ ] Validate                       | 

+------------------------------------------------------------+ 

- |  Suspects              |  Attempts                          | 

- |  1. users.py:create    |  #1  testsfailed  (KeyError)      | 

- |  2. validators.py:name |  #2  running...                    | 

- +------------------------------------------------------------+ 

- |  Patch (diff view)                  [ Download .diff ]      | 

- |  - name = data['username']                                  | 

|  + name = data.get('username', '').strip()                  | 

+------------------------------------------------------------+ 

- |  Tests:  FAILTOPASS 1/1 passed   PASSTOPASS 48/48 passed| 

+------------------------------------------------------------+ 

- The pipeline bar updates live from GET /runs/{id}/events. 

- Clicking an attempt expands its prompt, the LLM's response, and the raw test output, so a failed run can be understood. 

- The diff view shows removed lines in red and added lines in green, with the signs - and + as a second cue. 

- When the run ends, the header shows VERIFIED, FAILED, or ERROR with a one-line reason. 

# 6.4 Benchmark Summary screen 

text 

+------------------------------------------------------------+ 

|  Benchmark: SWE-bench Lite subset (30 tasks)                | 

- |  Model          Verified   Avg attempts   Avg tokens   Cost  | 

- |  gemini-flash   9/30       3.1            52k          $0.00 | 

|  groq-llama     6/30       3.8            47k          $0.00 | 

|  (numbers above are placeholders, not results)              | 

+------------------------------------------------------------+ 

- |  Failure reasons:  wrong file 11 | bad patch 6 | tests 4     | 

+------------------------------------------------------------+ 

This screen exists because the project's value comes from measurement and failure analysis, not a single demo. 

# 6.5 UI principles 

- Show progress immediately: the user should never stare at a blank page during a multi-minute run. 

- Show evidence, not just verdicts: every "verified" links to the patch and passing test output. 

- Accessible by default: text labels beside colours, keyboard-reachable buttons, readable contrast. 

- The CLI remains the main interface for batch work; the dashboard is for inspecting and demoing. 

# 7. Assumptions, dependencies and cost 

Codyssey can be built and tested at $0 using free LLM tiers, but their rate limits cap you at a few to about a dozen tasks per day. A final 30-task benchmark on a paid model is estimated at roughly $1 to $8. Prices and limits below were checked on 14 October 2026 and change often, so treat them as a snapshot and re-check before you commit. 

# 7.1 Assumptions 

- Version 1 targets Python repositories that use pytest, and tasks come from a small SWE-bench Lite subset (20 to 50 tasks). 

- Development happens on one laptop (assumed 16 GB RAM and at least 50 GB free disk, since Docker images for repositories are large) with Docker installed and internet access for LLM calls. 

- All LLM access is through API calls. No model is trained or fine-tuned. 

- The tests inside each task are trusted as the success signal, with the known weakness that a weak test can pass a wrong patch. 

- Benchmark repositories are public, so sending their code to a free-tier provider is acceptable. Private code should never be sent to a free tier (see 7.3). 

- Model names are stored in config.yaml, never hard-coded, because providers rename and retire models often. 

- 7.2 Software dependencies (all free and open source) 

| Library or tool | Used for | 

| --- | --- | 

| Python 3.11 or newer | Main language | 

| fastapi, uvicorn | REST API server | 

- | typer, rich | CLI commands and readable terminal output | 

- | pydantic | Validating inputs and defining data shapes | 

- | sqlalchemy (with SQLite) | Database access | 

- | docker (Python SDK) and Docker Engine or Docker Desktop | Sandbox containers | 

- | GitPython | Cloning repos and checking out commits | 

| pytest, coverage | Running tests and finding code touched by a failing test (inside the sandbox) | 

- | openai | One client for every provider that offers an OpenAI-style endpoint | 

- | google-genai | Official Gemini SDK, if the OpenAI-style endpoint is not used | 

- | tenacity | Retry with backoff on rate-limit errors | 

| React, Vite (or Streamlit) | Dashboard | 

Check Docker's licence terms for your situation before installing Docker Desktop. Docker Engine on Linux is a free alternative. 

- 7.3 Free and low-cost LLM APIs 

All five hosted options below can be called from Python, and the first four expose an OpenAI-compatible endpoint, so the OpenAICompatClient from section 4.3 covers them with a different baseurl. Prices are USD per 1 million tokens, input / output. 

| Provider | Free-tier models useful for Codyssey | Free-tier limits | Paid price (in / out) | 

| --- | --- | --- | --- | 

| [Google Gemini API](https://ai.google.dev/gemini-api/docs/pricing) | Gemini 3.8 Flash, 3.6 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite, 2.5 Pro, 2.5 Flash, 2.5 Flash-Lite | Per-project limits shown in AI Studio, not published in the docs; free-tier inputs and outputs may be used to improve Google's products | 3.8 Flash: $0.75 / $3.75 until 31 Dec 2026, then $1.50 / $7.50. 3.5 Flash-Lite: $0.30 / $2.50. 2.5 Flash-Lite: $0.10 / $0.40 | 

| [Groq](https://console.groq.com/docs/rate-limits) | openai/gpt-oss-120b, openai/gptoss-20b, qwen/qwen3.8-27b | No card. Listed as 30 requests/min, 1,000 requests/day, 8K tokens/min, 200K tokens/day per model | About $0.15 / $0.60 for gpt-oss-120b (thirdparty tracker) | 

| [OpenRouter](https://openrouter.ai/docs/api-reference/limits) | Any model whose ID ends in :free (the list rotates) | 20 requests/min; 50 requests/day, or 1,000/day once you have bought $10 of credits at any time | $0 for :free models | 

| [Cerebras](https://inference-docs.cerebras.ai/support/rate-limits) | gpt-oss-120b, qwen-3.8-27b | Trial only: $5 credit after adding a payment method, expiring in 30 days. 5 requests/min, 30K uncached tokens/min, 1M tokens/day | Pay as you go from $10 of credit; see the provider's pricing page | 

| [Mistral (Experiment plan)](https://anarlog.so/blog/mistral-api-key) | Mistral Small and Large families | No card. Reported as about 1B tokens/month and a low requests/min ceiling; free-plan requests may be used to train models. Figures are from third-party sources, so check the console | Small 3.2 about $0.10 / $0.30; Large 3 reported between $0.50 / $1.50 and $2 / $6 | 

| Ollama (local) | Open-weight models you download | Free, limited only by your laptop's RAM, GPU, and speed | $0 | 

What the limits mean for Codyssey: 

- Groq's free 8K tokens/min cannot take a 20K-token repo prompt. Use it only for short stages such as ranking suspect functions. 

- OpenRouter's 50 requests/day allows roughly 10 to 12 tasks per day at about 4 requests each, and a retry loop on a busy free model can use up the allowance without a usable answer. 

- Cerebras's 1M tokens/day allows roughly 14 tasks per day for the trial's 30 days, and its quota check counts your maxcompletiontokens setting in advance, so set it low. 

- Gemini's free tier is the best fit for development, because Google describes Gemini 3.8 Flash as built for long-horizon software engineering. Its Pro and Gemini 4 Argon models are not on the free tier. 

- Data privacy: on free tiers the provider may train on your prompts. Fine for public benchmark repos, not for private code. 

# 7.4 Recommended model plan 

1.  Development: Gemini 3.8 Flash on the free tier through the Google AI Studio key. 

2.  Short, cheap stages (localization ranking): Groq or Cerebras gpt-oss-120b. 

3.  Fallback when rate-limited: OpenRouter :free models, listed as several fallbacks in one request. 

4.  Final benchmark run: the same Gemini model on the paid tier, so results are not throttled and your prompts are not used for training. 

5.  Offline backup: Ollama with a small open model, accepting lower quality. 

# 7.5 Cost estimate 

Assumed tokens per task: one localization call (8K in, 0.5K out) plus 3 patch attempts (20K in, 1.5K out each). That is about 68K input and 5K output tokens per task, or 2.04M input and 0.15M output tokens for 30 tasks. These are planning guesses, so replace them with real numbers from the LLMCall log after your first runs. 

| Scenario (30 tasks) | Estimated cost | 

- | --- | --- | 

- | Any free tier | $0, but throttled to about 2 to 14 tasks per day depending on provider | 

| Gemini 3.5 Flash-Lite, paid | about $1.0 | 

| Gemini 3.8 Flash, paid, before 1 Jan 2027 | about $2.1 | 

| Gemini 3.8 Flash, paid, from 1 Jan 2027 | about $4.2 | 

| Worst case: every task uses the full 300K-token budget on Gemini 3.8 Flash, before 2027 | about $8.1 | 

Gemini bills thinking tokens as output. If output turns out to be three times the assumed amount, add about $1.1 to the 3.8 Flash estimate. Other costs: Docker and all libraries are free, and a cloud sandbox (Modal, E2B) is optional and not budgeted. 

7.6 Risks 

| Risk | Effect | Mitigation | 

| --- | --- | --- | 

| Free-tier limits or models change | Runs fail mid-experiment | Model IDs in config.yaml, fallback chain, check each provider's deprecation page before a benchmark | 

| Rate limits stall long runs | Slow progress | Backoff and a budget guard; run batches overnight | 

| Docker environment setup fails for some repos | Tasks skipped | Start with a fixed list of tasks that build cleanly; log skipped ones | 

| Weak tests pass a wrong patch | Inflated success rate | Re-run tests, review a sample of patches by hand | 

| Model has seen the public fixes | Memorization inflates results | Say so in the report; compare against a no-localization baseline | 

- | Prompts sent to free tiers are used for training | Private code leaks | Only public repos on free tiers | 

